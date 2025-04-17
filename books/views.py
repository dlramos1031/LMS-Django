from rest_framework import viewsets, permissions, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden
from .models import Author, Book, Genre, Borrowing
from .serializers import AuthorSerializer, BookSerializer, GenreSerializer, BorrowingSerializer
from django.utils.timezone import make_aware, now
from datetime import datetime
from users.decorators import admin_only

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

@login_required
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

@login_required
def book_detail_view(request, pk):
    book = get_object_or_404(Book, pk=pk)

    has_active_or_pending = Borrowing.objects.filter(
        user=request.user,
        book=book,
        status__in=['pending', 'approved'],
        is_active=True
    ).exists()

    return render(request, 'books/book_detail.html', {
        'book': book,
        'has_active_or_pending': has_active_or_pending,
    })

@login_required
def borrow_book_view(request, pk):
    book = get_object_or_404(Book, pk=pk)

    existing = Borrowing.objects.filter(
        user=request.user,
        book=book,
        status__in=['pending', 'approved'],
        is_active=True,
    ).exists()

    if existing:
        messages.warning(request, "You already have a pending or active borrow request for this book.")
        return redirect('book_detail', pk=pk)

    if request.method == 'POST':
        return_date_str = request.POST.get('return_date')
        try:
            return_date = make_aware(datetime.strptime(return_date_str, '%Y-%m-%d'))
        except ValueError:
            messages.error(request, "Invalid return date.")
            return redirect('book_detail', pk=pk)

        Borrowing.objects.create(
            user=request.user,
            book=book,
            return_date=return_date,
            status='pending',
            is_active=True,
        )

        messages.success(request, "Borrow request submitted! Please wait for librarian approval.")
        return redirect('books_list')

@admin_only
def librarian_dashboard_view(request):
    tab = request.GET.get('tab', 'pending')
    search = request.GET.get('search', '').strip()
    User = get_user_model()

    pending_qs = Borrowing.objects.filter(
        status='pending'
    ).select_related('book', 'user')

    active_qs = Borrowing.objects.filter(
        status='approved', is_active=True
    ).select_related('book', 'user')

    history_qs = Borrowing.objects.filter(
        status='approved', is_active=False
    ).select_related('book', 'user')

    book_qs = Book.objects.prefetch_related('authors', 'genres')
    user_qs = User.objects.all()

    if tab == 'pending' and search:
        pending_qs = pending_qs.filter(
            Q(book__title__icontains=search) | Q(user__username__icontains=search)
        )
    if tab == 'active' and search:
        active_qs = active_qs.filter(
            Q(book__title__icontains=search) | Q(user__username__icontains=search)
        )
    if tab == 'history' and search:
        history_qs = history_qs.filter(
            Q(book__title__icontains=search) | Q(user__username__icontains=search)
        )
    if tab == 'books' and search:
        book_qs = book_qs.filter(title__icontains=search)
    if tab == 'users' and search:
        user_qs = user_qs.filter(
            Q(username__icontains=search) |
            Q(full_name__icontains=search) |
            Q(email__icontains=search)
        )
        
    def paginate(queryset, per_page=6):
        paginator = Paginator(queryset, per_page)
        page = request.GET.get('page')
        return paginator.get_page(page)

    context = {
        'tab': tab,
        'now': now(),
        'pending_page': paginate(pending_qs) if tab == 'pending' else None,
        'active_page': paginate(active_qs) if tab == 'active' else None,
        'history_page': paginate(history_qs) if tab == 'history' else None,
        'book_page': paginate(book_qs) if tab == 'books' else None,
        'user_page': paginate(user_qs) if tab == 'users' else None,
    }
    return render(request, 'books/librarian_dashboard.html', context)

@staff_member_required
@require_POST
def approve_borrow_view(request, borrow_id):
    borrowing = get_object_or_404(Borrowing, pk=borrow_id, status='pending')
    borrowing.status = 'approved'
    borrowing.is_active = True
    borrowing.book.quantity -= 1
    borrowing.book.save()
    borrowing.save()
    messages.success(request, "Borrow request approved.")
    return redirect('librarian_dashboard')

@staff_member_required
@require_POST
def reject_borrow_view(request, borrow_id):
    borrowing = get_object_or_404(Borrowing, pk=borrow_id, status='pending')
    borrowing.status = 'rejected'
    borrowing.is_active = False
    borrowing.save()
    messages.warning(request, "Borrow request rejected.")
    return redirect('librarian_dashboard')

@staff_member_required
@require_POST
def mark_returned_view(request, borrow_id):
    borrowing = get_object_or_404(Borrowing, pk=borrow_id, status='approved', is_active=True)
    borrowing.status = 'returned'
    borrowing.is_active = False
    borrowing.book.quantity += 1
    borrowing.book.save()
    borrowing.save()
    messages.success(request, "Book marked as returned.")
    return redirect('librarian_dashboard')

@staff_member_required
@require_POST
def add_book_view(request):
    title = request.POST.get('title')
    quantity = request.POST.get('quantity')
    summary = request.POST.get('summary', '')
    book = Book.objects.create(title=title, quantity=quantity, summary=summary)
    book.open_library_id = request.POST.get('open_library_id', '')

    if 'cover_image' in request.FILES:
        book.cover_image = request.FILES['cover_image']

    authors_raw = request.POST.get('authors', '')
    for name in [n.strip() for n in authors_raw.split(',') if n.strip()]:
        author, _ = Author.objects.get_or_create(name=name)
        book.authors.add(author)

    genres_raw = request.POST.get('genres', '') 
    for name in [n.strip() for n in genres_raw.split(',') if n.strip()]:
        genre, _ = Genre.objects.get_or_create(name=name)
        book.genres.add(genre)

    book.save()
    messages.success(request, "Book added successfully.")
    return redirect('/dashboard/?tab=books')

@staff_member_required
@require_POST
def edit_book_view(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    book.title = request.POST.get('title')
    book.quantity = request.POST.get('quantity')
    book.summary = request.POST.get('summary', '')
    book.open_library_id = request.POST.get('open_library_id', '')

    if 'cover_image' in request.FILES:
        book.cover_image = request.FILES['cover_image']

    authors_raw = request.POST.get('authors', '')
    book.authors.clear()
    for name in [n.strip() for n in authors_raw.split(',') if n.strip()]:
        author, _ = Author.objects.get_or_create(name=name)
        book.authors.add(author)

    genres_raw = request.POST.get('genres', '')
    book.genres.clear()
    for name in [n.strip() for n in genres_raw.split(',') if n.strip()]:
        genre, _ = Genre.objects.get_or_create(name=name)
        book.genres.add(genre)

    book.save()
    messages.success(request, "Book updated successfully.")
    return redirect('/dashboard/?tab=books')

@staff_member_required
@require_POST
def delete_book_view(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    book.delete()
    messages.success(request, "Book deleted successfully.")
    return redirect('/dashboard/?tab=books')
