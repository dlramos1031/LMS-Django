from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django_filters import rest_framework as dj_filters
from django_filters.rest_framework import DjangoFilterBackend
from django.views.decorators.http import require_POST
from django.utils.timezone import make_aware, now
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.urls import reverse

from rest_framework import viewsets, permissions, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action

from datetime import datetime
from .models import Author, Book, Genre, Borrowing, Notification
from users.decorators import members_only, admin_only
from .serializers import (
    AuthorSerializer, 
    BookSerializer, 
    GenreSerializer, 
    BorrowingSerializer,
    NotificationSerializer
)

class BookFilter(dj_filters.FilterSet):
    genre = dj_filters.CharFilter(field_name='genres__name', lookup_expr='icontains')
    is_favorite = dj_filters.BooleanFilter(method='filter_is_favorite')

    class Meta:
        model = Book
        fields = ['authors'] 

    def filter_is_favorite(self, queryset, name, value):
        user = self.request.user
        if user.is_authenticated and value is True:
            return queryset.filter(favorited_by=user)
        return queryset

# ================================ View Sets ================================

class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

class GenreViewSet(viewsets.ModelViewSet):
    queryset = Genre.objects.all()
    serializer_class = GenreSerializer

class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all().prefetch_related('authors', 'genres', 'favorited_by')
    serializer_class = BookSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = BookFilter
    filterset_fields = ['authors', 'genres']
    search_fields = ['title', 'summary', 'authors__name']  

    @action(detail=True, methods=['post', 'delete'], permission_classes=[permissions.IsAuthenticated])
    def favorite(self, request, pk=None):
        book = self.get_object()
        user = request.user

        if request.method == 'POST':
            book.favorited_by.add(user)
            serializer = self.get_serializer(book)
            return Response(status=status.HTTP_200_OK)
        elif request.method == 'DELETE':
            book.favorited_by.remove(user)
            return Response(status=status.HTTP_204_NO_CONTENT)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        if notification.user != request.user:
             return Response({'detail': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
        notification.read = True
        notification.save()
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        Notification.objects.filter(user=request.user, read=False).update(read=True)
        return Response({'status': 'all marked as read'})

    @action(detail=False, methods=['delete'])
    def clear_all(self, request):
         Notification.objects.filter(user=request.user).delete()
         return Response(status=status.HTTP_204_NO_CONTENT)

def create_notification(user, title, message):
    Notification.objects.create(user=user, title=title, message=message)

class BorrowingViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BorrowingSerializer
    
    def list(self, request):
        borrowings = Borrowing.objects.filter(user=request.user)\
                                      .select_related('book')\
                                      .prefetch_related('book__authors', 'book__genres')\
                                      .order_by('-borrow_date')
        serializer = BorrowingSerializer(borrowings, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='request-borrow')
    def request_borrow(self, request):
        book_id = request.data.get('book_id')
        due_date_str = request.data.get('due_date')

        if not book_id or not due_date_str:
            return Response({"error": "book_id and due_date (YYYY-MM-DD) are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            book = Book.objects.get(pk=book_id)
        except Book.DoesNotExist:
            return Response({"error": "Book not found."}, status=status.HTTP_404_NOT_FOUND)

        existing_request = Borrowing.objects.filter(
            user=request.user,
            book=book,
            status__in=['pending', 'approved'],
            actual_return_date__isnull=True
        ).exists()
        if existing_request:
             return Response({"error": "You already have an active or pending borrow request for this book."}, status=status.HTTP_400_BAD_REQUEST)

        approved_count = Borrowing.objects.filter(book=book, status='approved', actual_return_date__isnull=True).count()
        if book.quantity <= approved_count:
            return Response({"error": "Book is currently not available."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            parsed_due_date = make_aware(datetime.strptime(due_date_str, '%Y-%m-%d'))
            if parsed_due_date <= now():
                 return Response({"error": "Due date must be in the future."}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
             return Response({"error": "Invalid due_date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        borrowing = Borrowing.objects.create(
            user=request.user,
            book=book,
            due_date=parsed_due_date, 
            status='pending',
        )
        serializer = BorrowingSerializer(borrowing, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='return')
    def return_book(self, request, pk=None):
        try:
            borrowing = Borrowing.objects.get(
                pk=pk,
                user=request.user,
                status='approved',
                actual_return_date__isnull=True 
            )
        except Borrowing.DoesNotExist:
            return Response({"error": "Approved borrowing record not found or not authorized."}, status=status.HTTP_404_NOT_FOUND)

        borrowing.status = 'returned'
        borrowing.actual_return_date = now() 
        borrowing.save(update_fields=['status', 'actual_return_date'])

        borrowing.book.quantity += 1
        borrowing.book.save(update_fields=['quantity'])

        serializer = BorrowingSerializer(borrowing, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK) 

    @action(detail=True, methods=['delete'], url_path='cancel-request') 
    def cancel_request(self, request, pk=None):
        try:
            borrowing = Borrowing.objects.get(pk=pk, user=request.user, status='pending')
        except Borrowing.DoesNotExist:
            return Response({"error": "Pending borrowing request not found or not authorized."}, status=status.HTTP_404_NOT_FOUND)

        borrowing.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@members_only
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

@members_only
def book_detail_view(request, pk):
    book = get_object_or_404(Book, pk=pk)

    has_active_or_pending = Borrowing.objects.filter(
        user=request.user,
        book=book,
        status__in=['pending', 'approved']
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
        status__in=['pending', 'approved']
    ).exists()

    if existing:
        messages.warning(request, "You already have a pending or active borrow request for this book.")
        return redirect('book_detail', pk=pk)

    if request.method == 'POST':
        due_date_str = request.POST.get('due_date')
        try:
            due_date = make_aware(datetime.strptime(due_date_str, '%Y-%m-%d'))
        except ValueError:
            messages.error(request, "Invalid return date.")
            return redirect('book_detail', pk=pk)

        Borrowing.objects.create(
            user=request.user,
            book=book,
            due_date=due_date,
            status='pending'
        )

        messages.success(request, "Borrow request submitted! Please wait for librarian approval.")
        return redirect('books_list')

# =========================== Librarian Dashboard ===========================

@admin_only
def librarian_dashboard_view(request):
    """
    Displays the librarian dashboard with different data sections based on the 'tab' query parameter.
    Handles search and pagination for each tab.
    Tabs: 'pending', 'active', 'history', 'books', 'users'.
    """
    # Determine active tab, default to 'pending'
    active_tab = request.GET.get('tab', 'pending').lower()
    valid_tabs = ['pending', 'active', 'history', 'books', 'users']
    if active_tab not in valid_tabs:
        active_tab = 'pending'

    # Get search term
    search = request.GET.get('search', '').strip()
    User = get_user_model()

    # --- Initial QuerySets ---
    # Pending: Status is 'pending'
    pending_qs = Borrowing.objects.filter(status='pending')\
                                   .select_related('book', 'user')

    # Active: Status is 'approved' AND actual_return_date is NULL
    active_qs = Borrowing.objects.filter(status='approved', actual_return_date__isnull=True)\
                                 .select_related('book', 'user')

    # History: Status is 'returned' OR 'rejected'
    history_qs = Borrowing.objects.filter(status__in=['returned', 'rejected'])\
                                  .select_related('book', 'user')

    # Books: All books
    book_qs = Book.objects.all().prefetch_related('authors', 'genres') # Keep prefetch

    # Users: All users
    user_qs = User.objects.all()

    # --- Apply Search Filters based on Active Tab ---
    if search:
        if active_tab == 'pending':
            pending_qs = pending_qs.filter(
                Q(book__title__icontains=search) | Q(user__username__icontains=search)
            )
        elif active_tab == 'active':
            active_qs = active_qs.filter(
                Q(book__title__icontains=search) | Q(user__username__icontains=search)
            )
        elif active_tab == 'history':
            history_qs = history_qs.filter(
                Q(book__title__icontains=search) | Q(user__username__icontains=search)
            )
        elif active_tab == 'books':
            # Add search across authors/genres if desired
            book_qs = book_qs.filter(
                 Q(title__icontains=search) |
                 Q(authors__name__icontains=search) |
                 Q(genres__name__icontains=search)
            ).distinct() # Use distinct because of M2M joins
        elif active_tab == 'users':
            user_qs = user_qs.filter(
                Q(username__icontains=search) |
                Q(full_name__icontains=search) | # Assuming you have full_name
                Q(email__icontains=search)
            )

    # --- Apply Ordering ---
    pending_qs = pending_qs.order_by('borrow_date') # Oldest pending first
    active_qs = active_qs.order_by('due_date') # Order by soonest due date
    history_qs = history_qs.order_by('-borrow_date') # Most recent history first
    book_qs = book_qs.order_by('title')
    user_qs = user_qs.order_by(User.USERNAME_FIELD)

    # --- Pagination Helper ---
    def paginate(queryset, per_page=10): # Adjust per_page as needed
        paginator = Paginator(queryset, per_page)
        page_number = request.GET.get('page')
        return paginator.get_page(page_number)

    # --- Prepare Context ---
    context = {
        'active_tab': active_tab, # Pass active tab name to template
        'search_term': search, # Pass search term back to template
        'now': now(), # Pass current time if needed in template
        # Paginate only the relevant queryset for the active tab
        'pending_page': paginate(pending_qs) if active_tab == 'pending' else None,
        'active_page': paginate(active_qs) if active_tab == 'active' else None,
        'history_page': paginate(history_qs) if active_tab == 'history' else None,
        'book_page': paginate(book_qs) if active_tab == 'books' else None,
        'user_page': paginate(user_qs) if active_tab == 'users' else None,
    }
    return render(request, 'books/librarian_dashboard.html', context)

# ========================= Librarian Borrowing Views =========================

@staff_member_required
@require_POST
def approve_borrow_view(request, borrow_id):
    borrowing = get_object_or_404(Borrowing, pk=borrow_id, status='pending')
    borrowing.status = 'approved'
    borrowing.save(update_fields=['status'])

    borrowing.book.quantity -= 1
    borrowing.book.save(update_fields=['quantity'])

    create_notification(
        user=borrowing.user, 
        title="Borrow Request Approved", 
        message=f"Your request to borrow '{borrowing.book.title}' has been approved."
    )

    messages.success(request, "Borrow request approved.")
    return redirect('librarian_dashboard')

@staff_member_required
@require_POST
def reject_borrow_view(request, borrow_id):
    borrowing = get_object_or_404(Borrowing, pk=borrow_id, status='pending')
    borrowing.status = 'rejected'
    borrowing.save(update_fields=['status'])

    create_notification(
        user=borrowing.user, 
        title="Borrow Request Rejected", 
        message=f"Your request to borrow '{borrowing.book.title}' has been rejected."
    )

    messages.warning(request, "Borrow request rejected.")
    return redirect('librarian_dashboard')

@staff_member_required
@require_POST
def mark_returned_view(request, borrow_id):
    borrowing = get_object_or_404(Borrowing, pk=borrow_id, status='approved')
    borrowing.status = 'returned'
    borrowing.actual_return_date = now() 
    borrowing.save(update_fields=['status', 'actual_return_date'])
    
    borrowing.book.quantity += 1
    borrowing.book.save(update_fields=['quantity'])

    create_notification(
        user=borrowing.user, 
        title="Book Returned!", 
        message=f"You have returned the book '{borrowing.book.title}' to the library."
    )

    messages.success(request, "Book marked as returned.")
    return redirect('librarian_dashboard')

# =========================== Librarian Book Views ===========================

@staff_member_required
@require_POST
def add_book_view(request):
    try:
        title = request.POST.get('title', '').strip()
        quantity_str = request.POST.get('quantity', '1').strip() 
        summary = request.POST.get('summary', '').strip()
        publisher = request.POST.get('publisher', '').strip()
        publish_date_str = request.POST.get('publish_date', '').strip()
        isbn_13 = request.POST.get('isbn_13', '').strip()
        isbn_10 = request.POST.get('isbn_10', '').strip()
        language = request.POST.get('language', '').strip()
        page_count_str = request.POST.get('page_count', '').strip()
        open_library_id = request.POST.get('open_library_id', '').strip()
        authors_raw = request.POST.get('authors', '').strip() 
        genres_raw = request.POST.get('genres', '').strip()

        if not title:
            messages.error(request, "Book title is required.")
            return redirect(f"{reverse('librarian_dashboard')}?tab=books")
        try:
            quantity = int(quantity_str)
            if quantity < 0: raise ValueError("Quantity cannot be negative.")
        except (ValueError, TypeError):
            messages.error(request, "Invalid quantity provided.")
            return redirect(f"{reverse('librarian_dashboard')}?tab=books")

        page_count = None
        if page_count_str:
            try:
                page_count = int(page_count_str)
                if page_count <= 0: raise ValueError("Page count must be positive.")
            except (ValueError, TypeError):
                messages.error(request, "Invalid page count provided.")
                return redirect(f"{reverse('librarian_dashboard')}?tab=books")

        publish_date = None
        if publish_date_str:
            try:
                publish_date = datetime.strptime(publish_date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, "Invalid publish date format. Use YYYY-MM-DD.")
                return redirect(f"{reverse('librarian_dashboard')}?tab=books")

        book = Book.objects.create(
            title=title,
            quantity=quantity,
            summary=summary or None,
            publisher=publisher or None,
            publish_date=publish_date,
            isbn_13=isbn_13 or None,
            isbn_10=isbn_10 or None,
            language=language or None,
            page_count=page_count,
            open_library_id=open_library_id or None
        )

        if 'cover_image' in request.FILES:
            book.cover_image = request.FILES['cover_image']
            # Save needed again after setting image if create didn't handle it
            # book.save(update_fields=['cover_image']) # Usually create handles it

        author_ids = []
        for name in [n.strip() for n in authors_raw.split(',') if n.strip()]:
            author, _ = Author.objects.get_or_create(name=name)
            author_ids.append(author.id)
        if author_ids:
            book.authors.set(author_ids) 

        genre_ids = []
        for name in [n.strip() for n in genres_raw.split(',') if n.strip()]:
            genre, _ = Genre.objects.get_or_create(name=name)
            genre_ids.append(genre.id)
        if genre_ids:
            book.genres.set(genre_ids) 

        book.save()
        messages.success(request, f"Book '{book.title}' added successfully.")
    except Exception as e:
         messages.error(request, f"Error adding book: {e}")

    return redirect(f"{reverse('librarian_dashboard')}?tab=books")

@staff_member_required
@require_POST
def edit_book_view(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    try:
        book.title = request.POST.get('title', book.title).strip()
        quantity_str = request.POST.get('quantity', str(book.quantity)).strip()
        book.summary = request.POST.get('summary', book.summary).strip()
        book.publisher = request.POST.get('publisher', book.publisher).strip() or None
        publish_date_str = request.POST.get('publish_date', '').strip()
        book.isbn_13 = request.POST.get('isbn_13', book.isbn_13).strip() or None
        book.isbn_10 = request.POST.get('isbn_10', book.isbn_10).strip() or None
        book.language = request.POST.get('language', book.language).strip() or None
        page_count_str = request.POST.get('page_count', '').strip()
        book.open_library_id = request.POST.get('open_library_id', book.open_library_id).strip() or None
        authors_raw = request.POST.get('authors', '').strip() 
        genres_raw = request.POST.get('genres', '').strip() 

        if not book.title:
            messages.error(request, "Book title cannot be empty.")
            return redirect(f"{reverse('librarian_dashboard')}?tab=books")
        try:
            book.quantity = int(quantity_str)
            if book.quantity < 0: raise ValueError("Quantity cannot be negative.")
        except (ValueError, TypeError):
            messages.error(request, "Invalid quantity provided.")
            return redirect(f"{reverse('librarian_dashboard')}?tab=books")

        if page_count_str:
            try:
                book.page_count = int(page_count_str)
                if book.page_count <= 0: raise ValueError("Page count must be positive.")
            except (ValueError, TypeError):
                messages.error(request, "Invalid page count provided.")
                return redirect(f"{reverse('librarian_dashboard')}?tab=books")
        else:
             book.page_count = None 

        if publish_date_str:
            try:
                book.publish_date = datetime.strptime(publish_date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, "Invalid publish date format. Use YYYY-MM-DD.")
                return redirect(f"{reverse('librarian_dashboard')}?tab=books")
        else:
             book.publish_date = None 

        if 'cover_image' in request.FILES:
            book.cover_image = request.FILES['cover_image']
        elif request.POST.get('clear_cover_image'): 
             book.cover_image = None

        author_ids = []
        for name in [n.strip() for n in authors_raw.split(',') if n.strip()]:
            author, _ = Author.objects.get_or_create(name=name)
            author_ids.append(author.id)
        book.authors.set(author_ids)

        genre_ids = []
        for name in [n.strip() for n in genres_raw.split(',') if n.strip()]:
            genre, _ = Genre.objects.get_or_create(name=name)
            genre_ids.append(genre.id)
        book.genres.set(genre_ids)

        book.save()
        messages.success(request, f"Book '{book.title}' updated successfully.")
    except Exception as e:
         messages.error(request, f"Error updating book: {e}")

    return redirect(f"{reverse('librarian_dashboard')}?tab=books")

@staff_member_required
@require_POST
def delete_book_view(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    active_borrowings = Borrowing.objects.filter(book=book, status='approved', actual_return_date__isnull=True).exists()
    if active_borrowings:
        messages.error(request, f"Cannot delete '{book.title}' as it is currently borrowed.")
        return redirect(f"{reverse('librarian_dashboard')}?tab=books")
    book.delete()
    messages.success(request, "Book deleted successfully.")
    return redirect(f"{reverse('librarian_dashboard')}?tab=books")
