from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, F, Count, Case, When, Exists, OuterRef
from django.urls import reverse_lazy, reverse
from datetime import datetime
from time import time
from uuid import uuid4
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.exceptions import PermissionDenied
from django.conf import settings
from decimal import Decimal
from datetime import date

# DRF Imports
from rest_framework import viewsets, permissions, status, generics, serializers, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

# User-related imports
from users.decorators import is_staff_user, StaffRequiredMixin
from users.models import CustomUser

# App-specific imports
from .filters import BookFilter
from .models import Author, Book, Category, BookCopy, Borrowing, Notification
from .serializers import (
    AuthorSerializer,
    BookSerializer,
    CategorySerializer,
    BookCopySerializer,
    BookCopyDetailSerializer,
    BorrowingSerializer,
    NotificationSerializer
)
# Assuming forms will be created in books/forms.py
from .forms import BookForm, BookCopyForm, CategoryForm, AuthorForm, IssueBookForm, ReturnBookForm, BatchAddBookCopyForm

CustomUser = get_user_model()

# --- Custom Permissions ---
class IsLibrarianOrAdminPermission(permissions.BasePermission):
    """
    Allows access only to authenticated users who are Librarians or Admins, or staff.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.role in ['LIBRARIAN', 'ADMIN'] or request.user.is_staff)
        )

# === DRF ViewSets ===
# (Your existing DRF ViewSets: AuthorViewSet, CategoryViewSet, BookViewSet,
#  BookCopyViewSet, BorrowingViewSet, NotificationViewSet remain here.
#  They are assumed to be largely correct for your API needs as per previous discussions.)

class AuthorViewSet(viewsets.ModelViewSet):
    """API endpoint for authors."""
    queryset = Author.objects.all().order_by('name')
    serializer_class = AuthorSerializer
    permission_classes = [IsLibrarianOrAdminPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'biography']
    ordering_fields = ['name', 'date_of_birth']
    filterset_fields = ['name']

class CategoryViewSet(viewsets.ModelViewSet):
    """API endpoint for categories."""
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [IsLibrarianOrAdminPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name']
    filterset_fields = ['name']

class BookViewSet(viewsets.ModelViewSet):
    """API endpoint for books."""
    queryset = Book.objects.all().prefetch_related('authors', 'categories', 'copies').order_by('title')
    serializer_class = BookSerializer
    lookup_field = 'isbn'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = BookFilter
    search_fields = ['title', 'isbn', 'authors__name', 'categories__name', 'description', 'publisher']
    ordering_fields = ['title', 'publication_date', 'total_borrows', 'date_added_to_system']
    ordering = ['title']
    
    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action in ['list', 'retrieve', 'available_copies_list']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [IsLibrarianOrAdminPermission]
        return [permission() for permission in permission_classes]

    @action(detail=True, methods=['get'], url_path='available-copies', permission_classes=[permissions.IsAuthenticated])
    def available_copies_list(self, request, isbn=None):
        book = self.get_object()
        available_copies = book.copies.filter(status='Available')
        serializer = BookCopySerializer(available_copies, many=True, context={'request': request})
        return Response(serializer.data)

class BookCopyViewSet(viewsets.ModelViewSet):
    """API endpoint for book copies."""
    queryset = BookCopy.objects.all().select_related('book').order_by('book__title', 'copy_id')
    permission_classes = [IsLibrarianOrAdminPermission]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['copy_id', 'book__title', 'book__isbn', 'condition_notes']
    ordering_fields = ['date_acquired', 'status', 'book__title', 'copy_id']
    filterset_fields = ['status', 'book__isbn', 'book__categories__name']

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return BookCopyDetailSerializer
        return BookCopySerializer

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        serializer.save()

class BorrowingViewSet(viewsets.ModelViewSet):
    """API endpoint for borrowing records."""
    serializer_class = BorrowingSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {
        'status': ['exact', 'in'],
        'borrower__username': ['exact', 'icontains'],
        'borrower__borrower_id_value': ['exact'],
        'book_copy__copy_id': ['exact'],
        'book_copy__book__isbn': ['exact'],
        'due_date': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'issue_date': ['exact', 'gte', 'lte', 'gt', 'lt'],
    }
    ordering_fields = ['issue_date', 'due_date', 'status', 'borrower__username']
    ordering = ['-issue_date']

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Borrowing.objects.none()
        if user.role in ['LIBRARIAN', 'ADMIN'] or user.is_staff:
            return Borrowing.objects.all().select_related('borrower', 'book_copy__book')
        return Borrowing.objects.filter(borrower=user).select_related('borrower', 'book_copy__book')

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action in ['list', 'retrieve', 'create']:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ['update', 'partial_update', 'destroy', 'return_book']:
            permission_classes = [IsLibrarianOrAdminPermission]
        else:
            permission_classes = [permissions.IsAuthenticated] 
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Handles creation of a borrowing record, potentially a request or direct loan."""
        instance = serializer.save()
        return instance

    @action(detail=True, methods=['post'], permission_classes=[IsLibrarianOrAdminPermission], url_path='return-book')
    def return_book(self, request, pk=None):
        borrowing_record = self.get_object()
        if borrowing_record.status not in ['ACTIVE', 'OVERDUE']:
            return Response(
                {'error': _('This book loan is not currently active or overdue.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        borrowing_record.return_date = timezone.now()
        book_copy_instance = borrowing_record.book_copy
        book_copy_instance.status = 'Available'
        book_copy_instance.save(update_fields=['status'])

        if isinstance(borrowing_record.due_date, datetime):
            due_date_as_date = borrowing_record.due_date.date()
        else:
            due_date_as_date = borrowing_record.due_date

        if borrowing_record.return_date.date() > due_date_as_date:
            borrowing_record.status = 'RETURNED_LATE'
            overdue_days = (borrowing_record.return_date.date() - due_date_as_date).days
            if overdue_days > 0: 
                fine_rate = Decimal(str(settings.FINE_RATE_PER_DAY_OVERDUE))
                borrowing_record.fine_amount = Decimal(overdue_days) * fine_rate
        else:
            borrowing_record.status = 'RETURNED'
        borrowing_record.save()
        Notification.objects.create(
            recipient=borrowing_record.borrower,
            notification_type='RETURN_CONFIRMED',
            message=_(f"Your loan for '{book_copy_instance.book.title}' has been returned.")
        )
        return Response(BorrowingSerializer(borrowing_record, context={'request': request}).data)
    
    @action(detail=True, methods=['post'], url_path='cancel-request', permission_classes=[permissions.IsAuthenticated])
    def cancel_request(self, request, pk=None):
        borrowing = self.get_object()
        if borrowing.borrower != request.user:
            return Response({'detail': 'You do not have permission to cancel this request.'}, status=status.HTTP_403_FORBIDDEN)
        if borrowing.status != 'REQUESTED':
            return Response({'detail': 'Only active requests (status "REQUESTED") can be cancelled.'}, status=status.HTTP_400_BAD_REQUEST)

        borrowing.status = 'CANCELLED'
        borrowing.save(update_fields=['status'])

        return Response({'detail': 'Borrow request cancelled successfully.'}, status=status.HTTP_200_OK)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for user notifications."""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['notification_type', 'is_read']
    ordering_fields = ['timestamp', 'notification_type']

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).order_by('-timestamp')

    @action(detail=False, methods=['get'], url_path='unread-count', permission_classes=[permissions.IsAuthenticated])
    def unread_count(self, request):
        """
        Returns the count of unread notifications for the currently authenticated user.
        """
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'unread_count': count}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='mark-all-read', permission_classes=[permissions.IsAuthenticated])
    def mark_all_as_read(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'detail': _('All notifications marked as read.')}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='mark-read', permission_classes=[permissions.IsAuthenticated])
    def mark_as_read(self, request, pk=None):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        return Response(NotificationSerializer(notification, context={'request': request}).data)


# --- API Views for Favorites Feature ---

class ToggleFavoriteAPIView(APIView):
    """
    API view to toggle a book's favorite status for the logged-in user.
    Expects a POST request to /api/books/<isbn>/toggle-favorite/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, isbn, format=None):
        user = request.user
        book = get_object_or_404(Book, isbn=isbn)

        if not hasattr(user, 'favorite_books') or not isinstance(user.favorite_books, list):
            user.favorite_books = [] # Initialize if attribute doesn't exist or is not a list

        is_currently_favorited = False
        # Check if the book is already in favorites
        for fav_item in user.favorite_books:
            if fav_item.get('isbn') == book.isbn:
                is_currently_favorited = True
                break
        
        if is_currently_favorited:
            # Remove from favorites
            user.favorite_books = [fav for fav in user.favorite_books if fav.get('isbn') != book.isbn]
            new_favorite_status = False
            action_message = _("'{title}' removed from your favorites.").format(title=book.title)
        else:
            # Add to favorites with timestamp
            user.favorite_books.append({
                "isbn": book.isbn,
                "favorited_at": timezone.now().isoformat()
            })
            new_favorite_status = True
            action_message = _("'{title}' added to your favorites.").format(title=book.title)

        user.save(update_fields=['favorite_books'])
        
        return Response({
            'status': 'success',
            'message': action_message,
            'is_favorite': new_favorite_status,
            'isbn': book.isbn
        }, status=status.HTTP_200_OK)

class ListFavoriteBooksAPIView(APIView):
    """
    API view to list all favorite books for the logged-in user.
    Sorts by newest favorited first.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        user = request.user
        
        if not hasattr(user, 'favorite_books') or not isinstance(user.favorite_books, list):
            favorite_items = []
        else:
            favorite_items = user.favorite_books

        # Sort favorites by 'favorited_at' timestamp in descending order (newest first)
        # Handle items that might be missing 'favorited_at' by placing them at the end or using a default past date
        def get_sort_key(item):
            timestamp_str = item.get('favorited_at')
            if timestamp_str:
                try:
                    return timezone.datetime.fromisoformat(timestamp_str)
                except ValueError: # Handle cases where timestamp might be malformed
                    return timezone.datetime.min.replace(tzinfo=timezone.utc) # or timezone.datetime.min
            return timezone.datetime.min.replace(tzinfo=timezone.utc) # Default for items without a timestamp

        sorted_favorites = sorted(favorite_items, key=get_sort_key, reverse=True)
        
        favorite_isbns = [fav.get('isbn') for fav in sorted_favorites if fav.get('isbn')]
        
        # Fetch book objects in the order of sorted_favorites
        # This preserves the sort order based on 'favorited_at'
        # We use a CASE WHEN to order by the list of ISBNs
        if favorite_isbns:
            preserved_order = Case(*[When(isbn=isbn, then=pos) for pos, isbn in enumerate(favorite_isbns)])
            favorite_books_queryset = Book.objects.filter(isbn__in=favorite_isbns).order_by(preserved_order)
        else:
            favorite_books_queryset = Book.objects.none()
            
        # Serialize the book data
        # Pass the request to the serializer context so 'is_favorite' can be determined (it will be true for all these)
        serializer = BookSerializer(favorite_books_queryset, many=True, context={'request': request})
        
        return Response(serializer.data, status=status.HTTP_200_OK)


@login_required
def my_notifications_view(request):
    # Ensure this view is only for borrowers, or adjust logic as needed
    if request.user.is_staff or request.user.role != 'BORROWER':
        messages.error(request, _("This page is for borrowers only."))
        return redirect('books:portal_catalog') # Or appropriate redirect

    user_notifications = Notification.objects.filter(recipient=request.user).order_by('-timestamp')
    
    # Paginate notifications
    paginator = Paginator(user_notifications, 15) # Show 15 notifications per page
    page_number = request.GET.get('page')
    try:
        notifications_page = paginator.page(page_number)
    except PageNotAnInteger:
        notifications_page = paginator.page(1)
    except EmptyPage:
        notifications_page = paginator.page(paginator.num_pages)

    context = {
        'notifications_page': notifications_page,
        'page_title': _('My Notifications'),
        'view_context': 'portal', # To maintain portal base template context
    }
    return render(request, 'users/portal/my_notifications.html', context)


# === Borrower Web Portal Views ===

class BookPortalCatalogView(ListView):
    model = Book
    template_name = 'books/portal/catalog.html'
    context_object_name = 'books'
    paginate_by = 12 

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related(
            'authors', 'categories', 'copies'
        )
        
        query_term = self.request.GET.get('q', '').strip()
        category_id_str = self.request.GET.get('category', '').strip()

        if query_term:
            queryset = queryset.filter(
                Q(title__icontains=query_term) |
                Q(authors__name__icontains=query_term) |
                Q(isbn__iexact=query_term)
            ).distinct()

        if category_id_str:
            try:
                category_id = int(category_id_str)
                queryset = queryset.filter(categories__id=category_id)
            except ValueError:
                pass 
        
        return queryset.order_by('title')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        context['page_title'] = _("Library Catalog")
        context['search_term'] = self.request.GET.get('q', '')
        context['all_categories'] = Category.objects.all().order_by('name')
        
        selected_category_id_str = self.request.GET.get('category', '')
        context['selected_category_id'] = selected_category_id_str
        context['selected_category_name'] = None
        if selected_category_id_str:
            try:
                selected_category = Category.objects.get(id=int(selected_category_id_str))
                context['selected_category_name'] = selected_category.name
                context['page_title'] = selected_category.name
            except (Category.DoesNotExist, ValueError):
                pass 

        SECTION_ITEM_LIMIT = 6

        # Home Favorites Section
        if user.is_authenticated:
            if hasattr(user, 'favorite_books') and isinstance(user.favorite_books, list):
                def get_sort_key(item):
                    timestamp_str = item.get('favorited_at')
                    if timestamp_str:
                        try: return timezone.datetime.fromisoformat(timestamp_str)
                        except ValueError: return timezone.datetime.min.replace(tzinfo=timezone.utc)
                    return timezone.datetime.min.replace(tzinfo=timezone.utc)
                sorted_favorites = sorted(user.favorite_books, key=get_sort_key, reverse=True)
                home_favorite_isbns = [fav.get('isbn') for fav in sorted_favorites[:SECTION_ITEM_LIMIT] if fav.get('isbn')]
                
                if home_favorite_isbns:
                    preserved_order = Case(*[When(isbn=isbn, then=pos) for pos, isbn in enumerate(home_favorite_isbns)])
                    context['home_favorite_books'] = Book.objects.filter(isbn__in=home_favorite_isbns).prefetch_related('authors').order_by(preserved_order)
                else:
                    context['home_favorite_books'] = Book.objects.none()
            else:
                context['home_favorite_books'] = Book.objects.none()
        else:
            context['home_favorite_books'] = Book.objects.none()

        # Newly Added Books Section
        context['newly_added_books'] = Book.objects.all().prefetch_related('authors').order_by('-date_added_to_system')[:SECTION_ITEM_LIMIT]

        # Recommendations Section
        excluded_isbns = set()
        if context.get('home_favorite_books'):
            excluded_isbns.update([b.isbn for b in context['home_favorite_books']])
        if context.get('newly_added_books'):
            excluded_isbns.update([b.isbn for b in context['newly_added_books']])
        
        context['recommended_books'] = Book.objects.exclude(
            isbn__in=list(excluded_isbns)
        ).prefetch_related('authors').order_by('-total_borrows', '?')[:SECTION_ITEM_LIMIT]

        # --- Recent Active Borrows (Corrected for Book Primary Key) ---
        if user.is_authenticated:
            recent_active_borrowings_qs = Borrowing.objects.filter(
                borrower=user, status__in=['ACTIVE', 'OVERDUE']
            ).select_related(
                'book_copy__book' 
            ).order_by('-issue_date')[:3]

            # Use .isbn as the primary key for Book model
            book_isbns_for_recent_borrows = [
                b.book_copy.book.isbn for b in recent_active_borrowings_qs 
                if b.book_copy and b.book_copy.book
            ]
            
            if book_isbns_for_recent_borrows:
                books_with_authors_map = {
                    book.isbn: book for book in Book.objects.filter(
                        isbn__in=book_isbns_for_recent_borrows
                    ).prefetch_related('authors')
                }
                context['recent_active_borrows'] = [
                    books_with_authors_map.get(b.book_copy.book.isbn) 
                    for b in recent_active_borrowings_qs 
                    if b.book_copy and b.book_copy.book and b.book_copy.book.isbn in books_with_authors_map
                ]
            else:
                context['recent_active_borrows'] = []
        else:
            context['recent_active_borrows'] = []
        # --- End Recent Active Borrows Correction ---

        query_params = self.request.GET.copy()
        if 'page' in query_params:
            del query_params['page']
        context['other_query_params'] = query_params.urlencode()
        
        return context
class BookPortalDetailView(DetailView):
    model = Book
    template_name = 'books/portal/book_detail.html'
    context_object_name = 'book'
    slug_field = 'isbn'
    slug_url_kwarg = 'isbn'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book_instance = self.get_object()
        user = self.request.user

        context['page_title'] = book_instance.title
        context['view_context'] = 'portal'

        # Check if the book is favorited by the current user
        is_favorite_book = False
        if user.is_authenticated:
            if hasattr(user, 'favorite_books') and isinstance(user.favorite_books, list):
                is_favorite_book = any(fav_item.get('isbn') == book_instance.isbn for fav_item in user.favorite_books)
        context['is_favorite_book'] = is_favorite_book

        # Borrower-specific flags and data
        if user.is_authenticated and not user.is_staff:
            active_or_pending_borrowing = Borrowing.objects.filter(
                borrower=user,
                book_copy__book=book_instance,
                status__in=['REQUESTED', 'ACTIVE', 'OVERDUE']
            ).first()
            context['active_or_pending_borrowing_for_this_book'] = active_or_pending_borrowing
            context['has_active_or_pending_request'] = active_or_pending_borrowing is not None
            context['available_book_copies_for_selection'] = book_instance.copies.filter(status='Available').order_by('date_acquired', 'id')
            
            can_borrow = book_instance.available_copies_count > 0 and not context['has_active_or_pending_request']
            context['can_reserve_this_book'] = book_instance.available_copies_count == 0 and not context['has_active_or_pending_request']
            context['can_borrow_this_book'] = can_borrow
        else:
            context['has_active_or_pending_request'] = False
            context['can_borrow_this_book'] = book_instance.available_copies_count > 0
            context['can_reserve_this_book'] = book_instance.available_copies_count == 0

        context['back_url'] = reverse_lazy('books:portal_catalog')
        context['available_book_copies'] = book_instance.copies.filter(status='Available')

        first_category = book_instance.categories.first()
        if first_category:
            context['related_books'] = Book.objects.filter(categories=first_category)\
                                           .exclude(isbn=book_instance.isbn)\
                                           .prefetch_related('authors', 'copies')\
                                           .annotate(available_copies_count=Count('copies', filter=Q(copies__status='Available')))\
                                           .distinct()[:4]
        return context

class FavoriteToggleView(LoginRequiredMixin, View):
    """
    Handles toggling the favorite status of a book for a logged-in user.
    Expects a POST request from a form.
    """
    def post(self, request, isbn):
        user = request.user
        book = get_object_or_404(Book, isbn=isbn)

        if not hasattr(user, 'favorite_books') or not isinstance(user.favorite_books, list):
            user.favorite_books = []

        is_currently_favorited = False
        # Check if the book is already in favorites
        for fav_item in user.favorite_books:
            if fav_item.get('isbn') == book.isbn:
                is_currently_favorited = True
                break
        
        if is_currently_favorited:
            user.favorite_books = [fav for fav in user.favorite_books if fav.get('isbn') != book.isbn]
            messages.success(request, _("'{title}' has been removed from your favorites.").format(title=book.title))
        else:
            user.favorite_books.append({
                "isbn": book.isbn,
                "favorited_at": timezone.now().isoformat()
            })
            messages.success(request, _("'{title}' has been added to your favorites.").format(title=book.title))
        
        user.save(update_fields=['favorite_books'])
        
        # Redirect back to the referring page or the book detail page
        # referrer = request.META.get('HTTP_REFERER', reverse('books:portal_book_detail', kwargs={'isbn': isbn}))
        return redirect(reverse('books:portal_book_detail', kwargs={'isbn': isbn}))


# New View for Listing User's Favorite Books (Web)
class MyFavoritesListView(LoginRequiredMixin, ListView):
    """
    Displays a list of books favorited by the logged-in user.
    """
    model = Book
    template_name = 'books/portal/my_favorites.html' # Create this template
    context_object_name = 'favorite_books'
    paginate_by = 10 # Optional pagination

    def get_queryset(self):
        user = self.request.user
        if not hasattr(user, 'favorite_books') or not isinstance(user.favorite_books, list) or not user.favorite_books:
            return Book.objects.none()

        def get_sort_key(item):
            timestamp_str = item.get('favorited_at')
            if timestamp_str:
                try:
                    return timezone.datetime.fromisoformat(timestamp_str)
                except ValueError:
                    return timezone.datetime.min.replace(tzinfo=timezone.utc)
            return timezone.datetime.min.replace(tzinfo=timezone.utc)

        sorted_favorites_data = sorted(user.favorite_books, key=get_sort_key, reverse=True)
        ordered_isbns = [fav_item['isbn'] for fav_item in sorted_favorites_data if fav_item.get('isbn')]

        if not ordered_isbns:
            return Book.objects.none()

        # Preserve the order based on 'favorited_at'
        preserved_order = Case(*[When(isbn=isbn, then=pos) for pos, isbn in enumerate(ordered_isbns)])
        return Book.objects.filter(isbn__in=ordered_isbns).order_by(preserved_order)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('My Favorite Books')
        return context

class PortalAuthorDetailView(DetailView):
    model = Author
    template_name = 'books/portal/author_detail.html'
    context_object_name = 'author'
    pk_url_kwarg = 'pk'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        author = self.get_object()
        context['page_title'] = f"Author: {author.name}"
        context['view_context'] = 'portal'
        context['can_edit_this_object'] = False
        context['books_by_author'] = Book.objects.filter(authors=author).prefetch_related('categories').order_by('title')
        context['back_url'] = self.request.META.get('HTTP_REFERER', reverse_lazy('books:portal_catalog'))
        return context
    

class StaffAuthorDetailView(StaffRequiredMixin, DetailView):
    model = Author
    template_name = 'books/dashboard/author_detail.html'
    context_object_name = 'author'
    pk_url_kwarg = 'pk'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        author = self.get_object()
        context['page_title'] = f"Author Details: {author.name}"
        context['view_context'] = 'dashboard'
        context['can_edit_this_object'] = self.request.user.is_staff
        context['books_by_author'] = Book.objects.filter(authors=author).prefetch_related('categories').order_by('title')
        context['back_url'] = reverse_lazy('books:dashboard_author_list')
        return context


class PortalCategoryDetailView(DetailView):
    model = Category
    template_name = 'books/portal/category_detail.html'
    context_object_name = 'category'
    pk_url_kwarg = 'pk'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category_instance = self.get_object()
        context['page_title'] = f"Category: {category_instance.name}"
        context['view_context'] = 'portal'
        context['can_edit_this_object'] = False
        context['books_in_category'] = Book.objects.filter(categories=category_instance).prefetch_related('authors').annotate(num_available_copies=Count('copies', filter=Q(copies__status='Available'))).order_by('title')
        context['back_url'] = self.request.META.get('HTTP_REFERER', reverse_lazy('books:portal_catalog'))
        return context
    

class StaffCategoryDetailView(StaffRequiredMixin, DetailView):
    model = Category
    template_name = 'books/dashboard/category_detail.html'
    context_object_name = 'category'
    pk_url_kwarg = 'pk'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category_instance = self.get_object()
        context['page_title'] = f"Category Details: {category_instance.name}"
        context['view_context'] = 'dashboard'
        context['can_edit_this_object'] = self.request.user.is_staff
        context['books_in_category'] = Book.objects.filter(categories=category_instance).prefetch_related('authors').annotate(num_available_copies=Count('copies', filter=Q(copies__status='Available'))).order_by('title')
        context['back_url'] = reverse_lazy('books:dashboard_category_list')
        return context


@login_required
@require_POST
def portal_create_borrow_request_view(request):
    """
    Handles a borrow request submitted by a logged-in user from the portal.
    Finds an available copy of the requested book and creates a 'REQUESTED' Borrowing record.
    """
    book_isbn = request.POST.get('book_isbn')
    requested_due_date_str = request.POST.get('due_date')
    selected_book_copy_id = request.POST.get('book_copy_id')

    if not request.user.is_authenticated or request.user.is_staff:
        messages.error(request, _("Only registered borrowers can request to borrow books."))
        if book_isbn:
            return redirect('books:portal_book_detail', isbn=book_isbn)
        return redirect('books:portal_catalog')

    if not book_isbn or not requested_due_date_str:
        messages.error(request, _("Book information or due date was missing in your request."))
        return redirect(request.META.get('HTTP_REFERER', 'books:portal_catalog'))

    book = get_object_or_404(Book, isbn=book_isbn)

    if Borrowing.objects.filter(
        borrower=request.user,
        book_copy__book=book,
        status__in=['REQUESTED', 'ACTIVE', 'OVERDUE']
    ).exists():
        messages.warning(request, _(f"You already have an active loan or pending request for '{book.title}'."))
        return redirect('books:portal_book_detail', isbn=book_isbn)

    target_copy = None
    if selected_book_copy_id:
        try:
            target_copy = BookCopy.objects.get(id=selected_book_copy_id, book=book, status='Available')
        except BookCopy.DoesNotExist:
            messages.error(request, _(f"The specific copy you selected is no longer available or invalid. Please try again."))
            return redirect('books:portal_book_detail', isbn=book_isbn)
    else:
        target_copy = BookCopy.objects.filter(book=book, status='Available').order_by('date_acquired', 'id').first()

    if not target_copy:
        messages.error(request, _(f"Sorry, no copies of '{book.title}' are currently available to request. Please try again later."))
        return redirect('books:portal_book_detail', isbn=book_isbn)

    try:
        due_date = datetime.strptime(requested_due_date_str, '%Y-%m-%d').date()
        today = timezone.now().date()
        if due_date <= today:
            messages.error(request, _("The preferred due date must be in the future."))
            return redirect('books:portal_book_detail', isbn=book_isbn)
        # Optional: Enforce max loan period for requested due date from library policy
        # max_due_date = today + timedelta(days=library_policy.MAX_LOAN_DAYS)
        # if due_date > max_due_date:
        #     messages.error(request, _(f"The preferred due date exceeds the maximum loan period of {library_policy.MAX_LOAN_DAYS} days."))
        #     return redirect('books:portal_book_detail', isbn=book_isbn)

    except ValueError:
        messages.error(request, _("Invalid due date format submitted."))
        return redirect('books:portal_book_detail', isbn=book_isbn)

    # Create the Borrowing record with status 'REQUESTED'
    try:
        Borrowing.objects.create(
            borrower=request.user,
            book_copy=target_copy,
            due_date=due_date,
            status='REQUESTED'
        )
        # Optionally, you could mark the available_copy as 'RESERVED_FOR_REQUEST' temporarily
        # available_copy.status = 'Reserved' # Or a new status 'PendingApproval'
        # available_copy.save()
        # This needs careful thought: if many request at once, which one gets it?
        # For now, we assume staff will see multiple requests if copies are available and pick.
        # Or, only one request per copy. A better system might lock the copy during request.

        messages.success(request, _(f"Your request for '{book.title}' (Copy ID: {target_copy.copy_id}) has been submitted."))
        return redirect('users:my_borrowings')

    except Exception as e:
        messages.error(request, _(f"An error occurred while submitting your request: {e}"))
        return redirect('books:portal_book_detail', isbn=book_isbn)


@login_required
def renew_book_view(request, borrowing_id): # Placeholder
    """Allows a logged-in user to request a renewal for an active loan."""
    borrowing = get_object_or_404(Borrowing, id=borrowing_id, borrower=request.user, status='ACTIVE')
    # TODO: Implement actual renewal logic
    # - Check library renewal policies (max renewals, not reserved by others).
    # - Update due_date.
    messages.info(request, _(f"Renewal feature for '{borrowing.book_copy.book.title}' is not yet implemented."))
    return redirect('users:my_borrowings')


# === Staff Dashboard Views ===

@login_required
def staff_dashboard_home_view(request):
    """Displays the main dashboard overview for staff members."""
    if not is_staff_user(request.user):
        messages.error(request, _("You do not have permission to access this page."))
        return redirect('books:portal_catalog')

    context = {
        'page_title': _("Staff Dashboard"),
        'book_title_count': Book.objects.count(),
        'book_copy_count': BookCopy.objects.count(),
        'active_loans_count': Borrowing.objects.filter(status='ACTIVE').count(),
        'overdue_loans_count': Borrowing.objects.filter(status='OVERDUE', return_date__isnull=True).count(),
        'total_borrowers_count': CustomUser.objects.filter(role='BORROWER').count(),
        'pending_requests_count': Borrowing.objects.filter(status='REQUESTED').count(),
    }
    return render(request, 'dashboard/home.html', context)


# --- Book & Collection Management (Staff) ---

class StaffBookDetailView(StaffRequiredMixin, DetailView):
    """
    Displays detailed information about a specific book for staff members.
    This view reuses the main book detail template but provides a 'dashboard' context.
    """
    model = Book
    template_name = 'books/dashboard/book_detail.html'
    context_object_name = 'book'
    slug_field = 'isbn'
    slug_url_kwarg = 'isbn'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book_instance = self.get_object()
        context['page_title'] = _(f"Book Details: {book_instance.title}")
        context['view_context'] = 'dashboard'
        context['can_edit_this_object'] = self.request.user.is_staff
        context['can_manage_copies'] = True
        context['back_url'] = reverse_lazy('books:dashboard_book_list')

        # Get all copies for this book (for the table on the book detail page)
        context['all_book_copies'] = book_instance.copies.all().order_by('copy_id')

        # Get current borrowings for this book (for the table on the book detail page)
        current_borrowings_qs = Borrowing.objects.filter(
            book_copy__book=book_instance,
            status__in=['ACTIVE', 'OVERDUE', 'REQUESTED']
        ).select_related('borrower', 'book_copy').annotate(
            status_order=Case(
                When(status__in=['ACTIVE', 'OVERDUE'], then=0),
                When(status='REQUESTED', then=1),
                default=2
            )
        ).order_by('status_order', 'issue_date')
        context['current_book_borrowings'] = current_borrowings_qs

        # These flags are for borrower actions, False for staff context
        context['has_active_or_pending_request'] = False
        context['can_borrow_this_book'] = False
        context['can_reserve_this_book'] = False
        context['is_favorite_book'] = False

        return context

class StaffBookListView(StaffRequiredMixin, ListView):
    """View for staff to list and manage book titles."""
    model = Book
    template_name = 'books/dashboard/book_management/book_list.html'
    context_object_name = 'books'
    paginate_by = 10

    def get_queryset(self):
        queryset = Book.objects.all()
        queryset = queryset.annotate(
            copy_count=Count('copies')
        )
        available_copies_subquery = BookCopy.objects.filter(
            book=OuterRef('pk'),
            status='Available'
        )
        queryset = queryset.annotate(
            has_available_copies=Exists(available_copies_subquery)
        )

        queryset = queryset.prefetch_related('authors', 'categories')

        search_term = self.request.GET.get('search', '').strip()
        category_id_filter = self.request.GET.get('category', '').strip()
        availability_filter = self.request.GET.get('availability', '').strip()

        if search_term:
            queryset = queryset.filter(
                Q(title__icontains=search_term) |
                Q(isbn__icontains=search_term) |
                Q(authors__name__icontains=search_term) |
                Q(categories__name__icontains=search_term) |
                Q(publisher__icontains=search_term)
            )
        
        if category_id_filter:
            queryset = queryset.filter(categories__id=category_id_filter)
            
        if availability_filter:
            if availability_filter == 'available':
                queryset = queryset.filter(has_available_copies=True)
            elif availability_filter == 'unavailable':
                queryset = queryset.filter(has_available_copies=False)

        return queryset.order_by('title').distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Manage Book Titles')
        context['current_search'] = self.request.GET.get('search', '')
        context['all_categories'] = Category.objects.all().order_by('name')
        context['current_category_filter'] = self.request.GET.get('category', '')
        context['current_availability_filter'] = self.request.GET.get('availability', '')
        
        query_params = self.request.GET.copy()
        query_params.pop('page', None) 
        context['other_query_params'] = query_params.urlencode()
        
        return context

class StaffBookCreateView(StaffRequiredMixin, CreateView):
    """View for staff to add a new book title."""
    model = Book
    form_class = BookForm
    template_name = 'books/dashboard/book_management/book_form.html'
    success_url = reverse_lazy('books:dashboard_book_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Add New Book Title')
        context['form_mode'] = 'create'
        return context

    def form_valid(self, form):
        messages.success(self.request, _(f"Book '{form.instance.title}' created successfully."))
        return super().form_valid(form)

class StaffBookUpdateView(StaffRequiredMixin, UpdateView):
    """View for staff to edit an existing book title."""
    model = Book
    form_class = BookForm
    template_name = 'books/dashboard/book_management/book_form.html'
    slug_field = 'isbn'
    slug_url_kwarg = 'isbn'

    def get_success_url(self):
        return reverse_lazy('books:dashboard_book_edit', kwargs={'isbn': self.object.isbn})


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Edit Book: {self.object.title}")
        context['form_mode'] = 'edit'
        context['book_copies'] = self.object.copies.all().order_by('copy_id')
        return context

    def form_valid(self, form):
        messages.success(self.request, _(f"Book '{form.instance.title}' updated successfully."))
        return super().form_valid(form)

class StaffBookDeleteView(StaffRequiredMixin, DeleteView):
    """View for staff to delete a book title and its copies."""
    model = Book
    template_name = 'books/dashboard/book_management/book_confirm_delete.html'
    slug_field = 'isbn'
    slug_url_kwarg = 'isbn'
    success_url = reverse_lazy('books:dashboard_book_list')
    context_object_name = 'book_to_delete'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Confirm Delete: {self.object.title}")
        return context

    def form_valid(self, form):
        if Borrowing.objects.filter(book_copy__book=self.object, status__in=['ACTIVE', 'OVERDUE', 'REQUESTED']).exists():
            messages.error(self.request, _(f"Cannot delete book '{self.object.title}' as some of its copies are involved in active transactions."))
            return redirect('books:dashboard_book_edit', isbn=self.object.isbn)
        messages.success(self.request, _(f"Book '{self.object.title}' and all its copies deleted successfully."))
        return super().form_valid(form)


# BookCopy Management Views

class StaffBookCopiesManageView(StaffRequiredMixin, DetailView):
    model = Book
    template_name = 'books/dashboard/book_management/bookcopy_list.html'
    context_object_name = 'book'
    slug_field = 'isbn'
    slug_url_kwarg = 'isbn'
    paginate_copies_by = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book_instance = self.get_object()
        context['page_title'] = _(f"Manage Copies for: {book_instance.title}")

        # Get copies related to this book
        copies_queryset = book_instance.copies.all().order_by('copy_id')

        # Get search and filter parameters from request
        search_copy_id = self.request.GET.get('search_copy_id', '').strip()
        status_filter = self.request.GET.get('status', '').strip()

        if search_copy_id:
            copies_queryset = copies_queryset.filter(copy_id__icontains=search_copy_id)
        
        if status_filter:
            copies_queryset = copies_queryset.filter(status=status_filter)

        # Paginate the copies_queryset
        paginator = Paginator(copies_queryset, self.paginate_copies_by)
        page_number = self.request.GET.get('page')
        try:
            paginated_copies = paginator.page(page_number)
        except PageNotAnInteger:
            paginated_copies = paginator.page(1)
        except EmptyPage:
            paginated_copies = paginator.page(paginator.num_pages)

        context['book_copies_page_obj'] = paginated_copies # Pass paginated object to template
        context['all_book_copies_count'] = copies_queryset.count() # Total count after filters

        # For repopulating filter form
        context['current_search_copy_id'] = search_copy_id
        context['current_status_filter'] = status_filter
        context['status_choices'] = BookCopy.STATUS_CHOICES

        # For pagination links, preserve other GET parameters
        query_params = self.request.GET.copy()
        if 'page' in query_params:
            del query_params['page']
        context['other_query_params'] = query_params.urlencode()

        return context

class StaffBookCopyCreateView(StaffRequiredMixin, CreateView):
    """View for staff to add a new copy of a book."""
    model = BookCopy
    form_class = BookCopyForm
    template_name = 'books/dashboard/book_management/bookcopy_form.html'

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.book = get_object_or_404(Book, isbn=self.kwargs.get('book_isbn'))

    def form_valid(self, form):
        form.instance.book = self.book
        messages.success(self.request, _(f"Copy '{form.cleaned_data.get('copy_id')}' for '{self.book.title}' added."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('books:dashboard_bookcopy_list', kwargs={'isbn': self.book.isbn})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f'Add Copy for "{self.book.title}"')
        context['book'] = self.book
        context['form_mode'] = 'create'
        return context
    
    def form_invalid(self, form): # For debugging: print form errors to the console
        print(f"BookCopyForm errors: {form.errors.as_json()}")
        for field, errors in form.errors.items():
            for error in errors:
                if field == '__all__':
                     messages.error(self.request, error)
                else:
                    messages.error(self.request, f"Error in '{form.fields[field].label if field in form.fields else field}': {error}")
        return super().form_invalid(form)

class StaffBatchAddBookCopiesView(StaffRequiredMixin, View):
    template_name = 'books/dashboard/book_management/batch_add_bookcopy_form.html'

    def get_book(self, book_isbn):
        return get_object_or_404(Book, isbn=book_isbn)

    def get(self, request, book_isbn):
        book = self.get_book(book_isbn)
        form = BatchAddBookCopyForm()
        context = {
            'form': form,
            'book': book,
            'page_title': _(f"Batch Add Copies for '{book.title}'")
        }
        return render(request, self.template_name, context)

    def post(self, request, book_isbn):
        book = self.get_book(book_isbn)
        form = BatchAddBookCopyForm(request.POST)
        if form.is_valid():
            number_of_copies = form.cleaned_data['number_of_copies']
            default_status = form.cleaned_data['default_status']
            date_acquired = form.cleaned_data['date_acquired']
            condition_notes = form.cleaned_data['condition_notes']
            copy_id_prefix = form.cleaned_data.get('copy_id_prefix', '').strip()

            new_copies = []
            for i in range(number_of_copies):
                # Generate a unique provisional copy_id
                # This is a simple approach; you might want something more robust or sequential
                # based on existing copy IDs for that book.
                timestamp_suffix = int(time() * 1000) # Milliseconds for more uniqueness
                unique_part = f"{timestamp_suffix}-{i+1}" 
                
                provisional_copy_id = f"{copy_id_prefix}{book.isbn}-{unique_part}"
                if len(provisional_copy_id) > 100: # Ensure it doesn't exceed max_length of copy_id
                    provisional_copy_id = provisional_copy_id[:97] + "..."


                # Check for extremely unlikely collision, loop to find a unique one
                while BookCopy.objects.filter(copy_id=provisional_copy_id).exists():
                    unique_part = f"{int(time() * 1000)}-{i+1}-{uuid4().hex[:4]}"
                    provisional_copy_id = f"{copy_id_prefix}{book.isbn}-{unique_part}"
                    if len(provisional_copy_id) > 100:
                         provisional_copy_id = provisional_copy_id[:97] + "..."
                
                new_copies.append(
                    BookCopy(
                        book=book,
                        copy_id=provisional_copy_id,
                        status=default_status,
                        date_acquired=date_acquired,
                        condition_notes=condition_notes
                    )
                )
            
            try:
                BookCopy.objects.bulk_create(new_copies)
                messages.success(request, _(f"{number_of_copies} new copies for '{book.title}' added successfully with provisional IDs. Please review and update IDs as needed."))
                return redirect('books:dashboard_bookcopy_list', isbn=book.isbn)
            except Exception as e:
                messages.error(request, _(f"An error occurred while adding copies: {e}"))

        context = {
            'form': form,
            'book': book,
            'page_title': _(f"Batch Add Copies for '{book.title}'")
        }
        return render(request, self.template_name, context)

class StaffBookCopyUpdateView(StaffRequiredMixin, UpdateView):
    """View for staff to edit an existing book copy."""
    model = BookCopy
    form_class = BookCopyForm
    template_name = 'books/dashboard/book_management/bookcopy_form.html'

    def get_success_url(self):
        return reverse_lazy('books:dashboard_bookcopy_list', kwargs={'isbn': self.object.book.isbn})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Edit Copy: {self.object.copy_id} for '{self.object.book.title}'")
        context['book'] = self.object.book
        context['form_mode'] = 'edit'
        return context

    def form_valid(self, form):
        messages.success(self.request, _(f"Copy '{form.instance.copy_id}' updated successfully."))
        return super().form_valid(form)

class StaffBookCopyDeleteView(StaffRequiredMixin, DeleteView):
    """View for staff to confirm and delete a specific book copy."""
    model = BookCopy
    template_name = 'books/dashboard/book_management/bookcopy_confirm_delete.html'
    context_object_name = 'bookcopy_to_delete'

    def get_success_url(self):
        """Redirect to the parent book's edit page after successful deletion."""
        if self.object and self.object.book:
            return reverse_lazy('books:dashboard_book_edit', kwargs={'isbn': self.object.book.isbn})
        return reverse_lazy('books:dashboard_book_list')

    def get_context_data(self, **kwargs):
        """Add page title to the context."""
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Confirm Delete Copy: {self.object.copy_id} for '{self.object.book.title}'")
        return context

    def delete(self, request, *args, **kwargs):
        """
        Handles the POST request to delete the object.
        Includes custom validation before deletion.
        """
        self.object = self.get_object() # Important to have the object instance
        
        # Custom validation: Check for active loans or requests
        if self.object.borrowings.filter(status__in=['ACTIVE', 'OVERDUE', 'REQUESTED']).exists():
            messages.error(request, _(f"Cannot delete copy '{self.object.copy_id}' as it is currently part of an active loan or request."))
            # Redirect back to the book edit page, as that's where "manage copies" usually is
            return redirect('books:dashboard_book_edit', isbn=self.object.book.isbn)

        success_url = self.get_success_url()
        copy_id_for_message = self.object.copy_id
        book_title_for_message = self.object.book.title

        response = super().delete(request, *args, **kwargs) # This performs the actual deletion

        messages.success(request, _(f"Copy '{copy_id_for_message}' for book '{book_title_for_message}' deleted successfully."))
        return response # super().delete() returns an HttpResponseRedirect to success_url

# Category Management Views
class StaffCategoryListView(StaffRequiredMixin, ListView):
    """View for staff to list and manage book categories."""
    model = Category
    form_class = CategoryForm
    template_name = 'books/dashboard/book_management/category_list.html'
    context_object_name = 'categories'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        search_term = self.request.GET.get('search', '').strip()
        if search_term:
            queryset = queryset.filter(
                Q(name__icontains=search_term) |
                Q(description__icontains=search_term)
            ).distinct()
        return queryset.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Manage Categories')
        context['current_search'] = self.request.GET.get('search', '')

        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['other_query_params'] = query_params.urlencode()
        return context

class StaffCategoryCreateView(StaffRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = 'books/dashboard/book_management/category_form.html'
    success_url = reverse_lazy('books:dashboard_category_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Add New Category')
        context['form_mode'] = 'create'
        return context

class StaffCategoryUpdateView(StaffRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'books/dashboard/book_management/category_form.html'
    success_url = reverse_lazy('books:dashboard_category_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Edit Category: {self.object.name}")
        context['form_mode'] = 'edit'
        return context

class StaffCategoryDeleteView(StaffRequiredMixin, DeleteView):
    model = Category
    template_name = 'books/dashboard/book_management/category_confirm_delete.html'
    success_url = reverse_lazy('books:dashboard_category_list')
    context_object_name = 'category_to_delete'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Confirm Delete Category: {self.object.name}")
        return context
    def form_valid(self, form):
        if self.object.books.exists():
            messages.error(self.request, _(f"Cannot delete category '{self.object.name}' as it's associated with books."))
            return redirect('books:dashboard_category_list')
        messages.success(self.request, _(f"Category '{self.object.name}' deleted successfully."))
        return super().form_valid(form)


# Author Management Views
class StaffAuthorListView(StaffRequiredMixin, ListView):
    """View for staff to list and manage authors."""
    model = Author
    template_name = 'books/dashboard/book_management/author_list.html'
    context_object_name = 'authors'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        search_term = self.request.GET.get('search', '').strip()
        if search_term:
            queryset = queryset.filter(
                Q(name__icontains=search_term) |
                Q(biography__icontains=search_term)
            ).distinct()
        return queryset.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Manage Authors')
        context['current_search'] = self.request.GET.get('search', '')

        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['other_query_params'] = query_params.urlencode()
        return context

class StaffAuthorCreateView(StaffRequiredMixin, CreateView):
    model = Author
    form_class = AuthorForm
    template_name = 'books/dashboard/book_management/author_form.html'
    success_url = reverse_lazy('books:dashboard_author_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Add New Author')
        context['form_mode'] = 'create'
        return context

class StaffAuthorUpdateView(StaffRequiredMixin, UpdateView):
    model = Author
    form_class = AuthorForm
    template_name = 'books/dashboard/book_management/author_form.html'
    success_url = reverse_lazy('books:dashboard_author_list')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Edit Author: {self.object.name}")
        context['form_mode'] = 'edit'
        return context

class StaffAuthorDeleteView(StaffRequiredMixin, DeleteView):
    model = Author
    template_name = 'books/dashboard/book_management/author_confirm_delete.html'
    success_url = reverse_lazy('books:dashboard_author_list')
    context_object_name = 'author_to_delete'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _(f"Confirm Delete Author: {self.object.name}")
        return context
    def form_valid(self, form):
        if self.object.books.exists():
            messages.error(self.request, _(f"Cannot delete author '{self.object.name}' as they are associated with books."))
            return redirect('books:dashboard_author_list')
        messages.success(self.request, _(f"Author '{self.object.name}' deleted successfully."))
        return super().form_valid(form)


# --- Circulation Management (Staff) ---
@login_required
@user_passes_test(is_staff_user)
def staff_issue_book_view(request):
    """
    Allows staff to manually issue an available book copy to a borrower.
    """
    if request.method == 'POST':
        form = IssueBookForm(request.POST)
        if form.is_valid():
            borrower = form.cleaned_data['borrower']
            book_copy = form.cleaned_data['book_copy']
            due_date = form.cleaned_data['due_date']

            current_time = timezone.now()

            if book_copy.status == 'Available':
                Borrowing.objects.create(
                    borrower=borrower,
                    book_copy=book_copy,
                    issue_date=current_time,
                    due_date=due_date,
                    status='ACTIVE',
                )
                book_copy.status = 'On Loan'
                book_copy.save(update_fields=['status'])

                book_title = book_copy.book
                book_title.total_borrows = F('total_borrows') + 1
                book_title.save(update_fields=['total_borrows'])
                book_title.refresh_from_db()

                Notification.objects.create(
                    recipient=borrower,
                    notification_type='BORROW_APPROVED',
                    message=_(f"The book '{book_copy.book.title}' (Copy: {book_copy.copy_id}) has been issued to you by library staff. It is due on {due_date.strftime('%B %d, %Y')}.")
                )
                messages.success(request, _(f"Book '{book_copy.book.title}' (Copy: {book_copy.copy_id}) issued to {borrower.username}."))
                return redirect('books:dashboard_active_loans')
            else:
                messages.error(request, _(f"Book copy '{book_copy.copy_id}' is no longer available. Current status: {book_copy.get_status_display()}"))
    else:
        form = IssueBookForm()

    context = {
        'form': form, 
        'page_title': _('Issue Book Manually')
    }
    return render(request, 'books/dashboard/circulation/issue_book.html', context)

@login_required
@user_passes_test(is_staff_user)
def staff_return_book_view(request):
    """Allows staff to mark a borrowed book copy as returned."""
    # form = ReturnBookForm(request.POST or None)
    # if request.method == 'POST' and form.is_valid():
    #     ... implement logic ...
    #     return redirect('books:dashboard_active_loans')
    # context = {'form': form, 'page_title': _('Return Book')}
    context = {'page_title': _('Return Book')} # Placeholder
    return render(request, 'books/dashboard/circulation/return_book.html', context)

class StaffPendingRequestsView(StaffRequiredMixin, ListView):
    """
    Displays a list of borrow requests that are pending staff approval.
    Ordered by the oldest request first.
    """
    model = Borrowing
    template_name = 'books/dashboard/circulation/pending_requests.html'
    context_object_name = 'pending_requests'
    paginate_by = 10

    def get_queryset(self):
        # Order by request_date to show oldest requests first (First Come, First Served)
        queryset = Borrowing.objects.filter(status='REQUESTED') \
                                    .select_related('borrower', 'book_copy__book') \
                                    .order_by('request_date')
        
        # Optional: Add search/filter by borrower username or book title
        search_term = self.request.GET.get('search', '').strip()
        if search_term:
            queryset = queryset.filter(
                Q(borrower__username__icontains=search_term) |
                Q(book_copy__book__title__icontains=search_term) |
                Q(book_copy__copy_id__icontains=search_term)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Pending Borrow Requests')
        context['current_search'] = self.request.GET.get('search', '')
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['other_query_params'] = query_params.urlencode()
        return context

@user_passes_test(is_staff_user)
@require_POST
def staff_approve_request_view(request, borrowing_id):
    """Approves a pending borrow request."""
    borrowing_request = get_object_or_404(Borrowing, id=borrowing_id, status='REQUESTED')
    book_copy = borrowing_request.book_copy
    if book_copy.status == 'Available':
        borrowing_request.status = 'ACTIVE'
        borrowing_request.issue_date = timezone.now()
        borrowing_request.save()
        book_copy.status = 'On Loan'
        book_copy.save()
        book_title = book_copy.book
        Book.objects.filter(pk=book_title.pk).update(total_borrows=F('total_borrows') + 1)
        Notification.objects.create(
            recipient=borrowing_request.borrower,
            notification_type='BORROW_APPROVED',
            message=f"Your request for '{book_copy.book.title}' has been approved. Due: {borrowing_request.due_date.strftime('%Y-%m-%d')}."
        )
        messages.success(request, _(f"Request for '{book_copy.book.title}' approved."))
    else:
        borrowing_request.status = 'REJECTED'
        borrowing_request.notes_by_librarian = f"Copy '{book_copy.copy_id}' became unavailable (Status: {book_copy.get_status_display()}) before approval."
        borrowing_request.save()
        Notification.objects.create(
            recipient=borrowing_request.borrower,
            notification_type='BORROW_REJECTED',
            message=f"Your request for '{book_copy.book.title}' could not be approved as the copy is no longer available."
        )
        messages.error(request, _(f"Could not approve. Copy '{book_copy.copy_id}' is not available."))
    return redirect('books:dashboard_pending_requests')

@user_passes_test(is_staff_user)
@require_POST
def staff_reject_request_view(request, borrowing_id):
    """Rejects a pending borrow request."""
    borrowing_request = get_object_or_404(Borrowing, id=borrowing_id, status='REQUESTED')
    borrowing_request.status = 'REJECTED'
    borrowing_request.save()
    Notification.objects.create(
        recipient=borrowing_request.borrower,
        notification_type='BORROW_REJECTED',
        message=f"Your request for '{borrowing_request.book_copy.book.title}' has been rejected."
    )
    messages.info(request, _(f"Request for '{borrowing_request.book_copy.book.title}' rejected."))
    return redirect('books:dashboard_pending_requests')


class StaffActiveLoansView(StaffRequiredMixin, ListView):
    """
    Displays a list of all currently active and overdue loans.
    Ordered by due date to prioritize those due soonest or already overdue.
    """
    model = Borrowing
    template_name = 'books/dashboard/circulation/active_loans.html'
    context_object_name = 'active_loans'
    paginate_by = 10

    def get_queryset(self):
        queryset = Borrowing.objects.filter(status__in=['ACTIVE', 'OVERDUE']) \
                                    .select_related('borrower', 'book_copy__book') \
                                    .order_by('due_date')

        search_term = self.request.GET.get('search', '').strip()
        status_filter = self.request.GET.get('status_filter', '').strip().upper()

        if search_term:
            queryset = queryset.filter(
                Q(borrower__username__icontains=search_term) |
                Q(borrower__first_name__icontains=search_term) |
                Q(borrower__last_name__icontains=search_term) |
                Q(book_copy__book__title__icontains=search_term) |
                Q(book_copy__copy_id__icontains=search_term) |
                Q(book_copy__book__isbn__icontains=search_term)
            )

        if status_filter:
            if status_filter == 'OVERDUE':
                queryset = queryset.filter(status='OVERDUE')
            elif status_filter == 'ACTIVE_NOT_OVERDUE':
                queryset = queryset.filter(status='ACTIVE', due_date__gte=timezone.now().date())
            elif status_filter == 'ACTIVE':
                queryset = queryset.filter(status='ACTIVE')
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Active & Overdue Loans')
        context['now_date'] = timezone.now().date()
        context['current_search'] = self.request.GET.get('search', '')
        
        context['status_filter_choices'] = [
            ('ACTIVE', _('Active')),
            ('OVERDUE', _('Overdue')),
        ]
        context['current_status_filter'] = self.request.GET.get('status_filter', '').upper()
        
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['other_query_params'] = query_params.urlencode()
        return context

class StaffBorrowingHistoryView(StaffRequiredMixin, ListView):
    """
    Displays a comprehensive history of all non-active borrowing records
    (e.g., returned, rejected, cancelled).
    """
    model = Borrowing
    template_name = 'books/dashboard/circulation/borrowing_history.html'
    context_object_name = 'borrowing_history'
    paginate_by = 15

    def get_queryset(self):
        # Define statuses that represent "historical" or "closed" records
        historical_statuses = [
            'RETURNED', 'RETURNED_LATE', 
            'REJECTED', 'CANCELLED', 
            'LOST_BY_BORROWER'
        ]
        
        queryset = Borrowing.objects.filter(status__in=historical_statuses) \
                                    .select_related('borrower', 'book_copy__book') \
                                    .order_by('-return_date', '-request_date') # Show most recently concluded first

        # --- Search Functionality ---
        search_term = self.request.GET.get('search', '').strip()
        status_filter = self.request.GET.get('status_filter', '').strip()

        if search_term:
            queryset = queryset.filter(
                Q(borrower__username__icontains=search_term) |
                Q(borrower__first_name__icontains=search_term) |
                Q(borrower__last_name__icontains=search_term) |
                Q(book_copy__book__title__icontains=search_term) |
                Q(book_copy__copy_id__icontains=search_term) |
                Q(book_copy__book__isbn__icontains=search_term)
            )
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        # --- End Search Functionality ---
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Borrowing History')

        context['current_search'] = self.request.GET.get('search', '')
        context['historical_status_choices'] = [
            choice for choice in Borrowing.STATUS_CHOICES 
            if choice[0] in ['RETURNED', 'RETURNED_LATE', 'REJECTED', 'CANCELLED', 'LOST_BY_BORROWER']
        ]
        context['current_status_filter'] = self.request.GET.get('status_filter', '')

        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['other_query_params'] = query_params.urlencode()

        return context

class BorrowingDetailView(LoginRequiredMixin, DetailView):
    model = Borrowing
    pk_url_kwarg = 'borrowing_id' # To match the URL
    context_object_name = 'borrowing'
    # Template will be decided based on view_context in get_context_data

    def get_object(self, queryset=None):
        """
        Override to ensure the user has permission to view this borrowing record.
        """
        borrowing = super().get_object(queryset)
        user = self.request.user

        if user == borrowing.borrower or is_staff_user(user):
            return borrowing
        else:
            raise PermissionDenied(_("You do not have permission to view this borrowing record."))

    def get_template_names(self):
        """
        Return a list of template names to be used for the request.
        This allows us to use different wrapper templates for portal vs dashboard.
        """
        if is_staff_user(self.request.user) and 'dashboard' in self.request.resolver_match.url_name:
            return ['books/dashboard/borrowing_detail.html']
        elif self.request.user == self.get_object().borrower: # Ensure it's the borrower for portal view
            return ['books/portal/borrowing_detail.html']
        else:
            # This case should ideally be caught by get_object's PermissionDenied,
            # but as a fallback, perhaps a generic access denied template.
            # Or, rely on the PermissionDenied to be handled by Django's default 403.html
            raise PermissionDenied(_("Template access unclear for your role."))


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        borrowing = self.object # The borrowing instance
        user = self.request.user

        # Determine view context
        is_staff_viewing = is_staff_user(user) and 'dashboard' in self.request.resolver_match.url_name
        
        if is_staff_viewing:
            context['view_context'] = 'dashboard'
            context['page_title'] = _(f"Borrowing Details: ID #{borrowing.id}")
            context['can_approve_request'] = borrowing.status == 'REQUESTED'
            context['can_reject_request'] = borrowing.status == 'REQUESTED'
            context['can_mark_returned'] = borrowing.status in ['ACTIVE', 'OVERDUE']
            context['can_cancel_request'] = False # Staff don't cancel, they reject
        elif user == borrowing.borrower: # Borrower's portal view
            context['view_context'] = 'portal'
            context['page_title'] = _("Borrowing Details")
            context['can_approve_request'] = False
            context['can_reject_request'] = False
            context['can_mark_returned'] = False
            context['can_cancel_request'] = borrowing.status == 'REQUESTED'
        else: # Should not happen due to get_object check
            context['view_context'] = 'portal' # Default, but access should be denied
            context['page_title'] = _("Borrowing Details")
            # Set all action flags to False
            context['can_approve_request'] = False
            context['can_reject_request'] = False
            context['can_mark_returned'] = False
            context['can_cancel_request'] = False

        # Common context items
        context['book'] = borrowing.book_copy.book
        context['book_copy'] = borrowing.book_copy
        context['borrower_profile'] = borrowing.borrower
        
        # For back button logic - can be refined
        # context['back_url'] = self.request.META.get('HTTP_REFERER', reverse_lazy('books:portal_catalog' if context['view_context'] == 'portal' else 'books:dashboard_home'))

        return context

def borrower_cancel_request_view(request, borrowing_id):
    """
    Allows a logged-in borrower to cancel their own 'REQUESTED' borrow request.
    """
    try:
        borrowing_request = get_object_or_404(
            Borrowing,
            id=borrowing_id,
            borrower=request.user, # Crucial: only the owner can cancel
            status='REQUESTED'     # Crucial: only cancellable if still requested
        )
    except Borrowing.DoesNotExist:
        messages.error(request, _("Borrowing request not found or you do not have permission to cancel it."))
        return redirect(request.META.get('HTTP_REFERER', reverse_lazy('users:my_borrowings'))) # Sensible fallback

    # Proceed to cancel
    borrowing_request.status = 'CANCELLED'
    # Optionally, add a note if your model supports it, e.g., borrowing_request.notes_by_borrower = "Cancelled by user."
    borrowing_request.save(update_fields=['status']) # Only update status field

    # Optional: Notify staff that a request was cancelled by the user, if desired
    # For example, by creating a Notification for staff or logging it.

    messages.success(request, _(f"Your request for '{borrowing_request.book_copy.book.title}' has been successfully cancelled."))
    
    # Redirect back to "My Borrowings" or the borrowing detail page itself
    # If redirecting to detail, ensure it handles the new 'CANCELLED' status gracefully
    return redirect(reverse_lazy('users:my_borrowings'))

@login_required
@user_passes_test(is_staff_user)
@require_POST
def staff_mark_loan_returned_view(request, borrowing_id):
    """
    Processes a book return by staff. Updates borrowing record and book copy status.
    Calculates fines for late returns.
    """
    if not is_staff_user(request.user): # Should be caught by decorator, but good practice
        messages.error(request, _("You do not have permission to perform this action."))
        return redirect('books:dashboard_home')

    loan = get_object_or_404(Borrowing, id=borrowing_id, status__in=['ACTIVE', 'OVERDUE'])
    book_copy_instance = loan.book_copy

    loan.actual_return_date = timezone.now() # Set the actual return time

    fine_amount_calculated = Decimal('0.00')
    fine_message_segment = ""

    # Check if the book is returned late
    # Ensure due_date is a date object for comparison with actual_return_date.date()
    if isinstance(loan.due_date, datetime): # If due_date is datetime object
        due_date_as_date = loan.due_date.date()
    else: # If due_date is already a date object
        due_date_as_date = loan.due_date

    if loan.actual_return_date.date() > due_date_as_date:
        loan.status = 'RETURNED_LATE'
        overdue_days = (loan.actual_return_date.date() - due_date_as_date).days
        if overdue_days > 0:
            # Use Decimal for currency calculations
            fine_rate = Decimal(str(settings.FINE_RATE_PER_DAY_OVERDUE))
            fine_amount_calculated = Decimal(overdue_days) * fine_rate
            loan.fine_amount = fine_amount_calculated
            fine_message_segment = _(f" A fine of ${fine_amount_calculated:.2f} has been applied for {overdue_days} day(s) overdue.")
        else: # Should not happen if actual_return_date.date() > due_date_as_date, but good for safety
            loan.fine_amount = Decimal('0.00')
    else:
        loan.status = 'RETURNED'
        loan.fine_amount = Decimal('0.00')

    loan.save()

    book_copy_instance.status = 'Available'
    book_copy_instance.save(update_fields=['status'])

    # Create Notification
    return_message_base = _(f"Book '{book_copy_instance.book.title}' (Copy: {book_copy_instance.copy_id}) has been successfully returned.")
    full_notification_message = return_message_base + fine_message_segment
    
    notification_type = 'RETURN_CONFIRMED'
    if loan.status == 'RETURNED_LATE' and fine_amount_calculated > 0:
        notification_type = 'FINE_ISSUED' 

    Notification.objects.create(
        recipient=loan.borrower,
        notification_type=notification_type,
        message=full_notification_message
    )
    messages.success(request, full_notification_message)
    
    # Redirect to active loans, or perhaps borrowing history if preferred
    return redirect('books:dashboard_active_loans')


@login_required
@user_passes_test(is_staff_user) 
def staff_mark_loan_lost_view(request, borrowing_id):
    """
    Allows staff to mark an active or overdue loan as 'LOST_BY_BORROWER'.
    Updates the BookCopy status to 'Lost' and applies a standard lost book fine.
    Shows a confirmation page before action.
    """
    loan = get_object_or_404(Borrowing, id=borrowing_id, status__in=['ACTIVE', 'OVERDUE'])
    book_copy_instance = loan.book_copy

    if request.method == 'POST':
        loan.status = 'LOST_BY_BORROWER'
        loan.return_date = timezone.now() # Mark a "return" date as the date it was declared lost
        
        # Apply the default lost book fine from settings
        lost_book_fine = Decimal(str(settings.DEFAULT_LOST_BOOK_FINE_AMOUNT))
        loan.fine_amount = lost_book_fine
        loan.save()

        book_copy_instance.status = 'Lost'
        book_copy_instance.save(update_fields=['status'])

        # Notify the borrower
        notification_message = _(
            f"The book '{book_copy_instance.book.title}' (Copy: {book_copy_instance.copy_id}) "
            f"that you borrowed has been marked as lost. "
            f"A fine of ${lost_book_fine:.2f} has been applied. "
            f"Please contact the library."
        )
        Notification.objects.create(
            recipient=loan.borrower,
            notification_type='FINE_ISSUED', # Or a more specific 'BOOK_LOST_FINE'
            message=notification_message
        )

        messages.success(request, _(
            f"Loan for '{book_copy_instance.book.title}' (Copy: {book_copy_instance.copy_id}) has been marked as 'Lost by Borrower'. "
            f"The book copy status is now 'Lost'. A fine of ${lost_book_fine:.2f} has been applied."
        ))
        
        return redirect('books:dashboard_borrowing_history') 

    context = {
        'loan': loan,
        'book_copy': book_copy_instance,
        'book': book_copy_instance.book,
        'page_title': _('Confirm Mark as Lost'),
        'default_lost_fine': Decimal(str(settings.DEFAULT_LOST_BOOK_FINE_AMOUNT)) # Pass fine to template
    }
    return render(request, 'books/dashboard/circulation/borrowing_confirm_lost.html', context)
