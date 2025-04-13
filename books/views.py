from rest_framework import viewsets, permissions, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from .models import Author, Book, Genre, Borrowing
from .serializers import AuthorSerializer, BookSerializer, GenreSerializer, BorrowingSerializer
from django.contrib.auth.decorators import login_required
from django.utils.timezone import make_aware
from datetime import datetime

class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

class GenreViewSet(viewsets.ModelViewSet):
    queryset = Genre.objects.all()
    serializer_class = GenreSerializer

class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['authors']  
    search_fields = ['title', 'summary']  

class BorrowingViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        borrowings = Borrowing.objects.filter(user=request.user).order_by('-borrow_date')
        serializer = BorrowingSerializer(borrowings, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def borrow(self, request):
        book_id = request.data.get('book')
        return_date = request.data.get('return_date')

        if not book_id or not return_date:
            return Response({"error": "Book and return_date are required."}, status=400)

        try:
            book = Book.objects.get(pk=book_id)
        except Book.DoesNotExist:
            return Response({"error": "Book not found."}, status=404)

        if book.quantity <= 0:
            return Response({"error": "Book is not available."}, status=400)

        borrowing = Borrowing.objects.create(
            user=request.user,
            book=book,
            return_date=return_date,
        )
        book.quantity -= 1
        book.total_borrows += 1
        book.save()

        return Response(BorrowingSerializer(borrowing).data, status=201)

    @action(detail=False, methods=['post'])
    def return_book(self, request):
        borrowing_id = request.data.get('id')

        try:
            borrowing = Borrowing.objects.get(pk=borrowing_id, user=request.user, status='borrowed')
        except Borrowing.DoesNotExist:
            return Response({"error": "Borrowing record not found."}, status=404)

        borrowing.status = 'returned'
        borrowing.save()

        borrowing.book.quantity += 1
        borrowing.book.save()

        return Response({"detail": "Book returned successfully."})

def books_list_view(request):
    search = request.GET.get("search", "")
    books = Book.objects.all()
    if search:
        books = books.filter(title__icontains=search)

    paginator = Paginator(books, 8) 
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "books/books_list.html", {
        "books": page_obj,
        "page_obj": page_obj,
        "search": search,
    })

def book_detail_view(request, pk):
    book = get_object_or_404(Book, pk=pk)
    return render(request, "books/book_detail.html", {"book": book})

@login_required
def borrow_book_view(request, pk):
    book = get_object_or_404(Book, pk=pk)

    if request.method == 'POST':
        return_date_str = request.POST.get('return_date')
        try:
            return_date = make_aware(datetime.strptime(return_date_str, '%Y-%m-%d'))
        except ValueError:
            messages.error(request, "Invalid return date.")
            return redirect('book_detail', pk=pk)

        if book.quantity <= 0:
            messages.error(request, "Book is not available.")
            return redirect('book_detail', pk=pk)

        Borrowing.objects.create(
            user=request.user,
            book=book,
            return_date=return_date
        )

        book.quantity -= 1
        book.total_borrows += 1
        book.save()

        messages.success(request, "Book borrowed successfully!")
        return redirect('books_list')