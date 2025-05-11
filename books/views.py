from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django_filters import rest_framework as dj_filters
from django_filters.rest_framework import DjangoFilterBackend
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView
from django.utils.timezone import make_aware, now
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.urls import reverse_lazy

from rest_framework import viewsets, permissions, filters, status, generics, serializers
from rest_framework.response import Response
from rest_framework.decorators import action

from datetime import datetime, timedelta
from .filters import BookFilter
from .models import Author, Book, Category, BookCopy, Borrowing, Notification
from users.decorators import members_only, admin_only
from .serializers import (
    AuthorSerializer, 
    BookSerializer, 
    CategorySerializer,
    BookCopySerializer, 
    BookCopyDetailSerializer, 
    BorrowingSerializer, 
    NotificationSerializer
)

CustomUser = get_user_model()


# --- Helper Functions for Permissions (Template Views) ---

def is_librarian_or_admin_user(user):
    """Checks if the user is a Librarian or Admin."""
    return user.is_authenticated and (user.role in ['LIBRARIAN', 'ADMIN'] or user.is_staff)

def is_admin_user(user):
    """Checks if the user is an Admin."""
    return user.is_authenticated and (user.role == 'ADMIN' or user.is_staff)


# --- DRF Permission Classes ---

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom DRF permission: Allows read-only access for any request,
    but write permissions only for admin users (is_staff or role='ADMIN').
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated and \
               (request.user.role == 'ADMIN' or request.user.is_staff)

class IsLibrarianOrAdminPermission(permissions.BasePermission):
    """
    Custom DRF permission: Allows access only to Librarian or Admin users.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and \
               (request.user.role in ['LIBRARIAN', 'ADMIN'] or request.user.is_staff)


# --- DRF ViewSets ---

class AuthorViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows authors to be viewed or edited.
    """
    queryset = Author.objects.all().order_by('name')
    serializer_class = AuthorSerializer
    permission_classes = [IsAdminOrReadOnly] 
    filter_backends = [DjangoFilterBackend, permissions.SearchFilter, permissions.OrderingFilter]
    search_fields = ['name', 'biography']
    ordering_fields = ['name', 'date_of_birth']
    filterset_fields = ['name']


class CategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows categories (formerly genres) to be viewed or edited.
    """
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, permissions.SearchFilter, permissions.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name']
    filterset_fields = ['name']


class BookViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows books to be viewed or edited.
    Uses ISBN as the lookup field.
    """
    queryset = Book.objects.all().prefetch_related('authors', 'categories', 'copies').order_by('title')
    serializer_class = BookSerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'isbn'

    filter_backends = [DjangoFilterBackend, permissions.SearchFilter, permissions.OrderingFilter]
    filterset_class = BookFilter
    search_fields = ['title', 'isbn', 'authors__name', 'categories__name', 'description', 'publisher']
    ordering_fields = ['title', 'publication_date', 'total_borrows', 'date_added_to_system']
    ordering = ['title']

    @action(detail=True, methods=['get'], url_path='available-copies', permission_classes=[permissions.IsAuthenticated])
    def available_copies_list(self, request, isbn=None):
        """Lists available copies for a specific book."""
        book = self.get_object()
        available_copies = book.copies.filter(status='Available')
        serializer = BookCopySerializer(available_copies, many=True, context={'request': request})
        return Response(serializer.data)

class BookCopyViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing individual Book Copies.
    Accessible by Librarians and Admins.
    """
    queryset = BookCopy.objects.all().select_related('book').order_by('book__title', 'copy_id')
    permission_classes = [IsLibrarianOrAdminPermission]
    filter_backends = [DjangoFilterBackend, permissions.SearchFilter, permissions.OrderingFilter]
    search_fields = ['copy_id', 'book__title', 'book__isbn', 'condition_notes']
    ordering_fields = ['date_acquired', 'status', 'book__title', 'copy_id']
    filterset_fields = ['status', 'book__isbn', 'book__categories__name']

    def get_serializer_class(self):
        """Return appropriate serializer class based on action."""
        if self.action in ['list', 'retrieve']:
            return BookCopyDetailSerializer
        return BookCopySerializer

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        serializer.save()


class BorrowingViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing borrowing records.
    Borrowers can view their own records. Librarians/Admins can manage all.
    """
    serializer_class = BorrowingSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, permissions.OrderingFilter]
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
        """
        Admins/Librarians see all borrowings.
        Borrowers see only their own borrowings.
        """
        user = self.request.user
        if user.role in ['LIBRARIAN', 'ADMIN'] or user.is_staff:
            return Borrowing.objects.all().select_related('borrower', 'book_copy__book')
        elif user.role == 'BORROWER':
            return Borrowing.objects.filter(borrower=user).select_related('borrower', 'book_copy__book')
        return Borrowing.objects.none()

    def perform_create(self, serializer):
        """
        Custom logic for creating a borrowing record (issuing a book).
        """
        borrower = self.request.user
        if 'borrower' in serializer.validated_data and \
           (self.request.user.role in ['LIBRARIAN', 'ADMIN'] or self.request.user.is_staff):
            borrower = serializer.validated_data['borrower']
        elif self.request.user.role != 'BORROWER' and 'borrower' not in serializer.validated_data:
            raise serializers.ValidationError(_("Librarian/Admin must specify a borrower."))

        book_copy_instance = serializer.validated_data['book_copy']
        if book_copy_instance.status != 'Available':
            raise serializers.ValidationError(
                _("This book copy (%(copy_id)s) is not available for borrowing. Its status is %(status)s.") % 
                {'copy_id': book_copy_instance.copy_id, 'status': book_copy_instance.get_status_display()}
            )

        due_date = now() + timedelta(days=14)
        instance = serializer.save(borrower=borrower, due_date=due_date, status='ACTIVE')
        book_copy_instance.status = 'On Loan'
        book_copy_instance.save(update_fields=['status'])

        Notification.objects.create(
            recipient=borrower,
            notification_type='BOOK_ISSUED',
            message=_(f"The book '{book_copy_instance.book.title}' (Copy ID: {book_copy_instance.copy_id}) has been issued to you. Due date: {due_date.strftime('%Y-%m-%d')}.")
        )

    @action(detail=True, methods=['post'], permission_classes=[IsLibrarianOrAdminPermission], url_path='return-book')
    def return_book(self, request, pk=None):
        """
        Action for a Librarian/Admin to mark a book as returned.
        """
        borrowing_record = self.get_object()
        if borrowing_record.status not in ['ACTIVE', 'OVERDUE']:
            return Response(
                {'error': _('This book loan is not currently active or overdue. It might have already been returned or cancelled.')}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        borrowing_record.actual_return_date = now()
        book_copy_instance = borrowing_record.book_copy
        
        book_copy_instance.status = 'Available'
        book_copy_instance.save(update_fields=['status'])

        # Update borrowing record status and calculate fines
        if borrowing_record.due_date < borrowing_record.actual_return_date.replace(tzinfo=None): # Ensure timezone awareness or make due_date naive for comparison if actual_return_date is naive
            borrowing_record.status = 'RETURNED_LATE'
            # Basic fine calculation (example: $1 per day overdue) - MAKE THIS CONFIGURABLE
            overdue_days = (borrowing_record.actual_return_date.date() - borrowing_record.due_date.date()).days
            if overdue_days > 0:
                borrowing_record.fine_amount = overdue_days * 1.00 # Example fine
        else:
            borrowing_record.status = 'RETURNED'
        
        borrowing_record.save()
        
        Notification.objects.create(
            recipient=borrowing_record.borrower,
            notification_type='RETURN_CONFIRMED',
            message=_(f"Your loan for '{book_copy_instance.book.title}' (Copy ID: {book_copy_instance.copy_id}) has been returned.")
        )
        
        return Response(BorrowingSerializer(borrowing_record, context={'request': request}).data)

    # Optional: Action for 'renew_book' if borrowers or staff can renew loans.


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows users to view their notifications.
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, permissions.OrderingFilter]
    filterset_fields = ['notification_type', 'is_read']
    ordering_fields = ['timestamp', 'notification_type']
    ordering = ['-timestamp']

    def get_queryset(self):
        """Users can only see their own notifications."""
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_as_read(self, request):
        """Marks all unread notifications for the current user as read."""
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'detail': _('All notifications marked as read.')}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        """Marks a specific notification for the current user as read."""
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        return Response(NotificationSerializer(notification, context={'request': request}).data)


# --- Django Template-Rendering Views (Borrower Web Portal & Staff Dashboard) ---

class BookPortalListView(ListView):
    """
    View for borrowers to see a list of all books in the web portal.
    """
    model = Book
    template_name = 'portal/book_list.html'
    context_object_name = 'books'
    paginate_by = 12

    def get_queryset(self):
        queryset = Book.objects.all().prefetch_related('authors', 'categories', 'copies').order_by('title')
        
        query = self.request.GET.get('q')
        category_filter_id = self.request.GET.get('category')

        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) |
                Q(authors__name__icontains=query) |
                Q(categories__name__icontains=query) |
                Q(isbn__iexact=query)
            ).distinct()
        
        if category_filter_id:
            try:
                category = Category.objects.get(id=category_filter_id)
                queryset = queryset.filter(categories=category)
            except (Category.DoesNotExist, ValueError):
                pass

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all().order_by('name')
        context['page_title'] = _("Library Catalog")
        
        current_category_id = self.request.GET.get('category')
        if current_category_id:
            try:
                context['current_category'] = Category.objects.get(id=current_category_id)
            except (Category.DoesNotExist, ValueError):
                pass
        return context


class BookPortalDetailView(DetailView):
    """
    View for borrowers to see details of a single book in the web portal.
    Uses ISBN for lookup.
    """
    model = Book
    template_name = 'portal/book_detail.html'
    context_object_name = 'book'
    slug_field = 'isbn'
    slug_url_kwarg = 'isbn'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book = self.get_object()
        context['page_title'] = book.title
        context['available_copies'] = book.copies.filter(status='Available')
        context['total_copies_count'] = book.copies.count()
        first_category = book.categories.first()
        if first_category:
            context['related_books'] = Book.objects.filter(categories=first_category)\
                                           .exclude(isbn=book.isbn)\
                                           .prefetch_related('authors', 'copies')\
                                           .distinct()[:4]
        return context


def books_by_category_portal_view(request, category_id=None, category_slug=None):
    """
    Lists books filtered by a specific category for the borrower portal.
    Can be accessed by category ID or a slug (if implemented on Category model).
    """
    selected_category = None
    if category_id:
        selected_category = get_object_or_404(Category, id=category_id)
    elif category_slug: # Assuming Category model might have a 'slug' field in the future
        # For now, let's assume slug is derived from name for simplicity in URL
        # This part would need a proper slug field on Category model for robustness
        category_name_from_slug = category_slug.replace('-', ' ').title()
        selected_category = get_object_or_404(Category, name__iexact=category_name_from_slug)
    else:
        return redirect('books:portal_book_list')

    books_in_category = Book.objects.filter(categories=selected_category)\
                            .prefetch_related('authors', 'copies')\
                            .order_by('title')
    
    paginator = Paginator(books_in_category, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'category': selected_category,
        'books': page_obj,
        'page_obj': page_obj,
        'page_title': _(f"Books in {selected_category.name}"),
        'all_categories': Category.objects.all().order_by('name'),
    }
    return render(request, 'portal/books_by_category_list.html', context)

class BookPortalDetailView(DetailView):
    """
    View for borrowers to see details of a single book in the web portal.
    Uses ISBN for lookup.
    """
    model = Book
    template_name = 'portal/book_detail.html'
    context_object_name = 'book'
    slug_field = 'isbn' # Using isbn (PK) as the slug for URL lookup
    slug_url_kwarg = 'isbn' # Matches the URL conf keyword for isbn

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book = self.get_object()
        context['page_title'] = book.title
        context['available_copies'] = book.copies.filter(status='Available')
        context['total_copies_count'] = book.copies.count() # Total physical copies
        # Example for related books (by first category, excluding self)
        first_category = book.categories.first()
        if first_category:
            context['related_books'] = Book.objects.filter(categories=first_category)\
                                           .exclude(isbn=book.isbn)\
                                           .prefetch_related('authors', 'copies')\
                                           .distinct()[:4] # Show up to 4 related books
        return context


def books_by_category_portal_view(request, category_id=None, category_slug=None): # Added category_slug
    """
    Lists books filtered by a specific category for the borrower portal.
    Can be accessed by category ID or a slug (if implemented on Category model).
    """
    selected_category = None
    if category_id:
        selected_category = get_object_or_404(Category, id=category_id)
    elif category_slug: # Assuming Category model might have a 'slug' field in the future
        # For now, let's assume slug is derived from name for simplicity in URL
        # This part would need a proper slug field on Category model for robustness
        category_name_from_slug = category_slug.replace('-', ' ').title()
        selected_category = get_object_or_404(Category, name__iexact=category_name_from_slug)
    else:
        return redirect('books:portal_book_list') # Redirect if no category identifier

    books_in_category = Book.objects.filter(categories=selected_category)\
                            .prefetch_related('authors', 'copies')\
                            .order_by('title')
    
    paginator = Paginator(books_in_category, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'category': selected_category,
        'books': page_obj, # For iterating in template
        'page_obj': page_obj, # For pagination controls
        'page_title': _(f"Books in {selected_category.name}"),
        'all_categories': Category.objects.all().order_by('name'),
    }
    return render(request, 'portal/books_by_category_list.html', context) # New template name


# --- Staff Dashboard Views ---

@login_required
@user_passes_test(is_librarian_or_admin_user, login_url=reverse_lazy('users:login'))
def staff_dashboard_home(request):
    """
    Main dashboard page for Librarians and Admins.
    """
    context = {
        'page_title': _("Staff Dashboard"),
        'book_title_count': Book.objects.count(), # Count of unique book titles
        'book_copy_count': BookCopy.objects.count(), # Total physical copies
        'active_loans_count': Borrowing.objects.filter(status='ACTIVE').count(),
        'overdue_loans_count': Borrowing.objects.filter(status='OVERDUE').count(),
        'total_borrowers_count': CustomUser.objects.filter(role='BORROWER').count(),
        # Add more stats as needed
    }
    return render(request, 'dashboard/staff_home.html', context) # Assumes 'dashboard/staff_home.html'

# Further staff views (CRUD for Books, Copies, Categories, Authors, Borrowings, Users)
# will be implemented using Django's Class-Based Views (ListView, CreateView, UpdateView, DeleteView)
# with appropriate LoginRequiredMixin and UserPassesTestMixin.
# Example (to be expanded later):
# class StaffBookListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
#     model = Book
#     template_name = 'dashboard/staff_book_list.html'
#     context_object_name = 'books'
#     paginate_by = 15
#     # test_func for UserPassesTestMixin
#     def test_func(self):
#         return is_librarian_or_admin_user(self.request.user)


# --- Template Views --- (Keep for compatibility with old templates, might remove in future)

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

# def book_detail_view(request, pk):
#     book = get_object_or_404(Book, pk=pk)
# 
#     has_active_or_pending = Borrowing.objects.filter(
#         user=request.user,
#         book=book,
#         status__in=['pending', 'approved']
#     ).exists()
# 
#     return render(request, 'books/book_detail.html', {
#         'book': book,
#         'has_active_or_pending': has_active_or_pending,
#     })
# 
# @login_required
# def borrow_book_view(request, pk):
#     book = get_object_or_404(Book, pk=pk)
# 
#     existing = Borrowing.objects.filter(
#         user=request.user,
#         book=book,
#         status__in=['pending', 'approved']
#     ).exists()
# 
#     if existing:
#         messages.warning(request, "You already have a pending or active borrow request for this book.")
#         return redirect('book_detail', pk=pk)
# 
#     if request.method == 'POST':
#         due_date_str = request.POST.get('due_date')
#         try:
#             due_date = make_aware(datetime.strptime(due_date_str, '%Y-%m-%d'))
#         except ValueError:
#             messages.error(request, "Invalid return date.")
#             return redirect('book_detail', pk=pk)
# 
#         Borrowing.objects.create(
#             user=request.user,
#             book=book,
#             due_date=due_date,
#             status='pending'
#         )
# 
#         messages.success(request, "Borrow request submitted! Please wait for librarian approval.")
#         return redirect('books_list')


# =========================== Librarian Dashboard ===========================


# --- Helper Function for Dashboard Views (Old) ---

def _get_dashboard_context(request, active_tab_name, queryset, search_fields=None):
    """Helper to handle search and pagination for dashboard views."""
    search = request.GET.get('search', '').strip()

    if search and search_fields:
        query = Q()
        for field in search_fields:
            query |= Q(**{f'{field}__icontains': search})
        
        if 'user__username' in search_fields and queryset.model == Borrowing:
            query |= Q(user__username__icontains=search)
        
        if 'book__title' in search_fields and queryset.model == Borrowing:
            query |= Q(book_copy__book__title__icontains=search)
        
        if queryset.model == Book:
            if 'authors__name' in search_fields:
                query |= Q(authors__name__icontains=search)
            if 'categories__name' in search_fields:
                query |= Q(categories__name__icontains=search)

        if queryset.model == Book and ('authors__name' in search_fields or 'categories__name' in search_fields):
            queryset = queryset.filter(query).distinct()
        elif queryset.model == CustomUser and ('first_name' in search_fields or 'email' in search_fields):
            queryset = queryset.filter(query).distinct() 
        else:
            queryset = queryset.filter(query)

    if queryset.model == Borrowing:
        if active_tab_name == 'pending': 
            queryset = queryset.order_by('issue_date') 
        elif active_tab_name == 'active':
            queryset = queryset.order_by('due_date') 
        elif active_tab_name == 'history':
            queryset = queryset.order_by('-issue_date')
    elif queryset.model == Book:
        queryset = queryset.order_by('title')
    elif queryset.model == CustomUser:
        queryset = queryset.order_by(CustomUser.USERNAME_FIELD)

    paginator = Paginator(queryset, 6)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'active_dashboard_tab': active_tab_name,
        'page_obj': page_obj,
        'search_term': search,
        'now': now(),
    }
    return context


@admin_only
def librarian_dashboard_view(request):
    return redirect('dashboard_pending')

@admin_only
def dashboard_pending_view(request):
    active_tab_name = 'pending'
    pending_qs = Borrowing.objects.filter(status='REQUESTED').select_related('book_copy__book', 'borrower')
    context = _get_dashboard_context(
        request,
        active_tab_name,
        pending_qs,
        search_fields=['book_copy__book__title', 'borrower__username']
    )
    return render(request, 'dashboard/pending_section.html', context)

@admin_only
def dashboard_active_view(request):
    active_tab_name = 'active'
    active_qs = Borrowing.objects.filter(status='ACTIVE', actual_return_date__isnull=True).select_related('book_copy__book', 'borrower')
    context = _get_dashboard_context(
        request,
        active_tab_name,
        active_qs,
        search_fields=['book_copy__book__title', 'borrower__username']
    )
    return render(request, 'dashboard/active_section.html', context)

@admin_only
def dashboard_history_view(request):
    active_tab_name = 'history'
    history_qs = Borrowing.objects.filter(status__in=['RETURNED', 'RETURNED_LATE', 'CANCELLED', 'LOST_BY_BORROWER']).select_related('book_copy__book', 'borrower')
    context = _get_dashboard_context(
        request,
        active_tab_name,
        history_qs,
        search_fields=['book_copy__book__title', 'borrower__username']
    )
    return render(request, 'dashboard/history_section.html', context)

@admin_only
def dashboard_books_view(request):
    active_tab_name = 'books'
    book_qs = Book.objects.all().prefetch_related('authors', 'categories')
    context = _get_dashboard_context(
        request,
        active_tab_name,
        book_qs,
        search_fields=['title', 'authors__name', 'categories__name', 'isbn']
    )
    context['all_books'] = Book.objects.all().prefetch_related('authors', 'categories')
    return render(request, 'dashboard/books_section.html', context)

# ========================= Librarian Borrowing Views =========================

# @staff_member_required
# @require_POST
# def approve_borrow_view(request, borrow_id):
#     borrowing = get_object_or_404(Borrowing, pk=borrow_id, status='pending')
#     borrowing.status = 'approved'
#     borrowing.save(update_fields=['status'])
# 
#     borrowing.book.quantity -= 1
#     borrowing.book.total_borrows += 1
#     borrowing.book.save(update_fields=['quantity'])
# 
#     create_notification(
#         user=borrowing.user, 
#         title="Borrow Request Approved", 
#         message=f"Your request to borrow '{borrowing.book.title}' has been approved."
#     )
# 
#     messages.success(request, "Borrow request approved.")
#     return redirect('dashboard_pending')
# 
# @staff_member_required
# @require_POST
# def reject_borrow_view(request, borrow_id):
#     borrowing = get_object_or_404(Borrowing, pk=borrow_id, status='pending')
#     borrowing.status = 'rejected'
#     borrowing.save(update_fields=['status'])
# 
#     create_notification(
#         user=borrowing.user, 
#         title="Borrow Request Rejected", 
#         message=f"Your request to borrow '{borrowing.book.title}' has been rejected."
#     )
# 
#     messages.warning(request, "Borrow request rejected.")
#     return redirect('dashboard_pending')
# 
# @staff_member_required
# @require_POST
# def mark_returned_view(request, borrow_id):
#     borrowing = get_object_or_404(Borrowing, pk=borrow_id, status='approved')
#     borrowing.status = 'returned'
#     borrowing.actual_return_date = now() 
#     borrowing.save(update_fields=['status', 'actual_return_date'])
#     
#     borrowing.book.quantity += 1
#     borrowing.book.save(update_fields=['quantity'])
# 
#     create_notification(
#         user=borrowing.user, 
#         title="Book Returned!", 
#         message=f"You have returned the book '{borrowing.book.title}' to the library."
#     )
# 
#     messages.success(request, "Book marked as returned.")
#     return redirect('dashboard_active')


# =========================== Librarian Book Views ===========================

@staff_member_required
@require_POST
def add_book_view(request):
    try:
        title = request.POST.get('title', '').strip()
        initial_copies_str = request.POST.get('initial_copies', '1').strip()
        summary = request.POST.get('summary', '').strip()
        publisher = request.POST.get('publisher', '').strip()
        publish_date_str = request.POST.get('publish_date', '').strip()
        isbn_val = request.POST.get('isbn', '').strip()
        page_count_str = request.POST.get('page_count', '').strip()

        authors_raw = request.POST.get('authors', '').strip() 
        categories_raw = request.POST.get('categories', '').strip()

        if not title or not isbn_val:
            messages.error(request, "Book title and ISBN are required.")
            return redirect('books:dashboard_books_v1')
        
        if Book.objects.filter(isbn=isbn_val).exists():
            messages.error(request, f"A book with ISBN {isbn_val} already exists.")
            return redirect('books:dashboard_books_v1')

        try:
            initial_copies = int(initial_copies_str)
            if initial_copies < 0: raise ValueError("Number of copies cannot be negative.")
        except (ValueError, TypeError):
            messages.error(request, "Invalid number of initial copies provided.")
            return redirect('books:dashboard_books_v1')
        
        page_count = None
        if page_count_str:
            try:
                page_count = int(page_count_str)
                if page_count <= 0: raise ValueError("Page count must be positive.")
            except (ValueError, TypeError):
                messages.error(request, "Invalid page count provided. Must be a number.")
                return redirect('books:dashboard_books_v1')

        publish_date = None
        if publish_date_str:
            try:
                publish_date = datetime.strptime(publish_date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, "Invalid publish date format. Use YYYY-MM-DD.")
                return redirect('books:dashboard_books_v1')

        book = Book.objects.create(
            isbn=isbn_val,
            title=title,
            description=summary or None,
            publisher=publisher or None,
            publication_date=publish_date,
            page_count=page_count,
        )

        if 'cover_image_url' in request.POST:
            book.cover_image_url = request.POST.get('cover_image_url', '').strip() or None

        author_ids = []
        for name in [n.strip() for n in authors_raw.split(',') if n.strip()]:
            author, _ = Author.objects.get_or_create(name=name)
            author_ids.append(author.id)
        if author_ids:
            book.authors.set(author_ids) 

        category_ids_list = []
        for name in [n.strip() for n in categories_raw.split(',') if n.strip()]:
            category_obj, _ = Category.objects.get_or_create(name=name)
            category_ids_list.append(category_obj.id)
        if category_ids_list:
            book.categories.set(category_ids_list)

        book.save()

        for i in range(initial_copies):
            unique_copy_id_part = BookCopy.objects.filter(book=book).count() + 1
            copy_id_val = f"{book.isbn}-C{unique_copy_id_part}" 
            BookCopy.objects.create(book=book, copy_id=copy_id_val, status='Available')

        messages.success(request, f"Book '{book.title}' and {initial_copies} cop(y/ies) added successfully.")
    except Exception as e:
         messages.error(request, f"Error adding book: {e}")

    return redirect('books:dashboard_books_v1')


@staff_member_required
@require_POST
def edit_book_view(request, book_isbn):
    book = get_object_or_404(Book, isbn=book_isbn)
    try:
        book.title = request.POST.get('title', book.title).strip()

        book.description = request.POST.get('summary', book.description).strip()
        book.publisher = request.POST.get('publisher', book.publisher).strip() or None
        publish_date_str = request.POST.get('publish_date', '').strip()
        page_count_str = request.POST.get('page_count', '').strip()

        
        authors_raw = request.POST.get('authors', '').strip() 
        categories_raw = request.POST.get('categories', '').strip()

        if not book.title:
            messages.error(request, "Book title cannot be empty.")
            return redirect('books:dashboard_books_v1')

        if page_count_str:
            try:
                book.page_count = int(page_count_str)
                if book.page_count <= 0: raise ValueError("Page count must be positive.")
            except (ValueError, TypeError):
                messages.error(request, "Invalid page count provided.")
                return redirect('books:dashboard_books_v1')
        else:
             book.page_count = None 

        if publish_date_str:
            try:
                book.publish_date = datetime.strptime(publish_date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, "Invalid publish date format. Use YYYY-MM-DD.")
                return redirect('books:dashboard_books_v1')
        else:
             book.publish_date = None 

        if 'cover_image_url' in request.POST:
            book.cover_image_url = request.POST.get('cover_image_url', '').strip() or None
        elif request.POST.get('clear_cover_image_url'): 
             book.cover_image_url = None

        author_ids = []
        for name in [n.strip() for n in authors_raw.split(',') if n.strip()]:
            author, _ = Author.objects.get_or_create(name=name)
            author_ids.append(author.id)
        book.authors.set(author_ids)

        category_ids_list = []
        for name in [n.strip() for n in categories_raw.split(',') if n.strip()]:
            category_obj, _ = Category.objects.get_or_create(name=name)
            category_ids_list.append(category_obj.id)
        book.categories.set(category_ids_list)

        book.save()
        messages.success(request, f"Book '{book.title}' updated successfully.")
    except Exception as e:
         messages.error(request, f"Error updating book: {e}")

    return redirect('books:dashboard_books_v1')


@staff_member_required
@require_POST
def delete_book_view(request, book_isbn):
    book = get_object_or_404(Book, isbn=book_isbn)
    
    if Borrowing.objects.filter(book_copy__book=book, status__in=['ACTIVE', 'OVERDUE', 'REQUESTED']).exists():
        messages.error(request, f"Cannot delete '{book.title}' as one or more of its copies are currently involved in active or pending loans.")
        return redirect('books:dashboard_books_v1')
    
    book_title_for_message = book.title
    book.delete()
    messages.success(request, f"Book '{book_title_for_message}' and all its copies deleted successfully.")
    return redirect('books:dashboard_books_v1')
