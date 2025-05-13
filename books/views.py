from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, F, Count, Case, When, BooleanField
from django.urls import reverse_lazy
from datetime import datetime

# DRF Imports
from rest_framework import viewsets, permissions, status, generics, serializers, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend

# User-related imports
from users.decorators import is_staff_user, StaffRequiredMixin

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
from .forms import BookForm, BookCopyForm, CategoryForm, AuthorForm, IssueBookForm, ReturnBookForm

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
    permission_classes = [IsLibrarianOrAdminPermission]
    lookup_field = 'isbn'
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = BookFilter
    search_fields = ['title', 'isbn', 'authors__name', 'categories__name', 'description', 'publisher']
    ordering_fields = ['title', 'publication_date', 'total_borrows', 'date_added_to_system']
    ordering = ['title']

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
    permission_classes = [IsLibrarianOrAdminPermission]
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
        if not user.is_authenticated: # Should be caught by permission_classes but good practice
            return Borrowing.objects.none()
        if user.role in ['LIBRARIAN', 'ADMIN'] or user.is_staff:
            return Borrowing.objects.all().select_related('borrower', 'book_copy__book')
        return Borrowing.objects.filter(borrower=user).select_related('borrower', 'book_copy__book')

    def perform_create(self, serializer):
        """Handles creation of a borrowing record, potentially a request or direct loan."""
        borrower = self.request.user
        if 'borrower' in serializer.validated_data and \
           (self.request.user.role in ['LIBRARIAN', 'ADMIN'] or self.request.user.is_staff):
            borrower = serializer.validated_data['borrower']
        elif not (self.request.user.role in ['LIBRARIAN', 'ADMIN'] or self.request.user.is_staff) and \
             'borrower' in serializer.validated_data and serializer.validated_data['borrower'] != self.request.user:
            raise serializers.ValidationError(_("You can only request books for yourself."))
        elif (self.request.user.role in ['LIBRARIAN', 'ADMIN'] or self.request.user.is_staff) and \
             'borrower' not in serializer.validated_data and 'book_copy' in serializer.validated_data:
             pass

        book_copy_instance = serializer.validated_data['book_copy']
        if book_copy_instance.status != 'Available':
            raise serializers.ValidationError(
                _("This book copy (%(copy_id)s) is not available for borrowing. Its status is %(status)s.") %
                {'copy_id': book_copy_instance.copy_id, 'status': book_copy_instance.get_status_display()}
            )

        requested_due_date = serializer.validated_data.get('due_date')
        status_val = 'REQUESTED'
        due_date_val = requested_due_date or (timezone.now() + datetime.timedelta(days=14))

        # Staff might directly create an 'ACTIVE' loan via API
        if self.request.user.role in ['LIBRARIAN', 'ADMIN'] or self.request.user.is_staff:
            if 'status' in serializer.validated_data: # Allow staff to set status
                 status_val = serializer.validated_data['status']

        instance = serializer.save(borrower=borrower, due_date=due_date_val, status=status_val)

        if instance.status == 'ACTIVE':
            book_copy_instance.status = 'On Loan'
            book_copy_instance.save(update_fields=['status'])
            Notification.objects.create(
                recipient=borrower,
                notification_type='BORROW_APPROVED',
                message=_(f"The book '{book_copy_instance.book.title}' has been issued. Due: {instance.due_date.strftime('%Y-%m-%d')}.")
            )
        elif instance.status == 'REQUESTED':
             Notification.objects.create( # Assuming you have a BORROW_REQUESTED type
                recipient=borrower,
                notification_type='BORROW_REQUESTED',
                message=_(f"Your request for '{book_copy_instance.book.title}' has been submitted.")
            )
        return instance # serializer.save returns the instance

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

        if borrowing_record.due_date.date() < borrowing_record.return_date.date():
            borrowing_record.status = 'RETURNED_LATE'
            overdue_days = (borrowing_record.return_date.date() - borrowing_record.due_date.date()).days
            if overdue_days > 0: # Ensure positive fine
                borrowing_record.fine_amount = overdue_days * 1.00 # Example fine
        else:
            borrowing_record.status = 'RETURNED'
        borrowing_record.save()
        Notification.objects.create(
            recipient=borrowing_record.borrower,
            notification_type='RETURN_CONFIRMED',
            message=_(f"Your loan for '{book_copy_instance.book.title}' has been returned.")
        )
        return Response(BorrowingSerializer(borrowing_record, context={'request': request}).data)

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for user notifications."""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['notification_type', 'is_read']
    ordering_fields = ['timestamp', 'notification_type']

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).order_by('-timestamp')

    @action(detail=False, methods=['post'], url_path='mark-all-read', permission_classes=[permissions.IsAuthenticated])
    def mark_all_as_read(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'detail': _('All notifications marked as read.')}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='mark-read', permission_classes=[permissions.IsAuthenticated])
    def mark_as_read(self, request, pk=None): # Renamed for consistency with how it might be used
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        return Response(NotificationSerializer(notification, context={'request': request}).data)


# === Borrower Web Portal Views ===

class BookPortalCatalogView(ListView):
    """Displays a paginated list of books for borrowers."""
    model = Book
    template_name = 'books/portal/catalog.html'
    context_object_name = 'books'
    paginate_by = 12

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related('authors', 'categories').annotate(
            num_available_copies=Count('copies', filter=Q(copies__status='Available'))
        )
        query = self.request.GET.get('q')
        category_id = self.request.GET.get('category')

        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) |
                Q(authors__name__icontains=query) |
                Q(categories__name__icontains=query) |
                Q(isbn__iexact=query)
            ).distinct()
        if category_id:
            queryset = queryset.filter(categories__id=category_id)
        return queryset.order_by('title')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all().order_by('name')
        context['page_title'] = _("Library Catalog")
        context['search_term'] = self.request.GET.get('q', '')
        context['selected_category_id'] = self.request.GET.get('category', '')
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

        context['page_title'] = book_instance.title
        context['view_context'] = 'portal'

        # Borrower-specific flags and data
        if self.request.user.is_authenticated and not self.request.user.is_staff:
            has_request = Borrowing.objects.filter(
                borrower=self.request.user,
                book_copy__book=book_instance,
                status__in=['REQUESTED', 'ACTIVE']
            ).exists()
            context['has_active_or_pending_request'] = has_request
            
            can_borrow = book_instance.available_copies_count > 0 and not has_request
            context['can_borrow_this_book'] = can_borrow
            context['can_reserve_this_book'] = book_instance.available_copies_count == 0 and not has_request
            
            # TODO: Implement favorite logic if desired
            # context['is_favorite_book'] = Favorite.objects.filter(user=self.request.user, book=book_instance).exists()
            context['is_favorite_book'] = False # Placeholder
        else: # For guests or staff viewing portal page (staff won't typically use portal actions)
            context['has_active_or_pending_request'] = False
            context['can_borrow_this_book'] = book_instance.available_copies_count > 0
            context['can_reserve_this_book'] = book_instance.available_copies_count == 0
            context['is_favorite_book'] = False

        context['back_url'] = reverse_lazy('books:portal_catalog')
        
        # Common details needed by the template
        # context['available_book_copies'] is used by the borrow modal in the template currently
        context['available_book_copies'] = book_instance.copies.filter(status='Available')

        first_category = book_instance.categories.first()
        if first_category:
            context['related_books'] = Book.objects.filter(categories=first_category)\
                                           .exclude(isbn=book_instance.isbn)\
                                           .prefetch_related('authors', 'copies')\
                                           .annotate(available_copies_count=Count('copies', filter=Q(copies__status='Available')))\
                                           .distinct()[:4]
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

    if not request.user.is_authenticated or request.user.is_staff:
        messages.error(request, _("Only registered borrowers can request to borrow books."))
        if book_isbn:
            return redirect('books:portal_book_detail', isbn=book_isbn)
        return redirect('books:portal_catalog')

    if not book_isbn or not requested_due_date_str:
        messages.error(request, _("Book information or due date was missing in your request."))
        return redirect(request.META.get('HTTP_REFERER', 'books:portal_catalog'))

    book = get_object_or_404(Book, isbn=book_isbn)

    existing_request_or_loan = Borrowing.objects.filter(
        borrower=request.user,
        book_copy__book=book,
        status__in=['REQUESTED', 'ACTIVE', 'OVERDUE']
    ).exists()

    if existing_request_or_loan:
        messages.warning(request, _(f"You already have an active loan or pending request for '{book.title}'."))
        return redirect('books:portal_book_detail', isbn=book_isbn)

    available_copy = BookCopy.objects.filter(book=book, status='Available').first()

    if not available_copy:
        messages.error(request, _(f"Sorry, no copies of '{book.title}' are currently available to request. Please try reserving or check back later."))
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
            book_copy=available_copy, # Assign the found available copy
            # request_date is auto_now_add
            due_date=due_date, # User's preferred due date
            status='REQUESTED'
            # issue_date will be set by staff upon approval
        )
        # Optionally, you could mark the available_copy as 'RESERVED_FOR_REQUEST' temporarily
        # available_copy.status = 'Reserved' # Or a new status 'PendingApproval'
        # available_copy.save()
        # This needs careful thought: if many request at once, which one gets it?
        # For now, we assume staff will see multiple requests if copies are available and pick.
        # Or, only one request per copy. A better system might lock the copy during request.

        messages.success(request, _(f"Your request to borrow '{book.title}' (Copy ID: {available_copy.copy_id}) has been submitted. Please await staff approval. You requested to return it by {due_date.strftime('%B %d, %Y')}."))
        # Redirect to "My Borrowings" or "My Pending Requests" page
        return redirect('books:portal_book_detail', isbn=book_isbn) 

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
        queryset = super().get_queryset().prefetch_related('authors', 'categories').annotate(
            copy_count=Count('copies'),
            has_available_copies=Case(
                When(copies__status='Available', then=True),
                default=False,
                output_field=BooleanField()
            )
        ).distinct()

        search_term = self.request.GET.get('search', '').strip()
        category_filter = self.request.GET.get('category', '').strip()
        availability_filter = self.request.GET.get('availability', '').strip()

        if search_term:
            queryset = queryset.filter(
                Q(title__icontains=search_term) |
                Q(isbn__icontains=search_term) |
                Q(authors__name__icontains=search_term) |
                Q(categories__name__icontains=search_term) |
                Q(publisher__icontains=search_term)
            )
        
        if category_filter:
            queryset = queryset.filter(categories__id=category_filter)
            
        if availability_filter:
            if availability_filter == 'available':
                queryset = queryset.filter(has_available_copies=True)
            elif availability_filter == 'unavailable':
                queryset = queryset.filter(has_available_copies=False)

        return queryset.order_by('title')

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book_instance = self.get_object()
        context['page_title'] = _(f"Manage Copies for: {book_instance.title}")
        context['book_copies'] = book_instance.copies.all().order_by('copy_id')
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

@user_passes_test(is_staff_user)
@require_POST
def staff_mark_loan_returned_view(request, borrowing_id):
    """
    Processes a book return by staff. Updates borrowing record and book copy status.
    Calculates fines if applicable.
    """
    if not is_staff_user(request.user):
        messages.error(request, _("You do not have permission to perform this action."))
        return redirect('books:dashboard_home')

    loan = get_object_or_404(Borrowing, id=borrowing_id, status__in=['ACTIVE', 'OVERDUE'])
    book_copy_instance = loan.book_copy

    loan.actual_return_date = timezone.now()

    fine_amount_calculated = 0
    if loan.due_date.date() < loan.actual_return_date.date():
        loan.status = 'RETURNED_LATE'
        overdue_days = (loan.actual_return_date.date() - loan.due_date.date()).days
        if overdue_days > 0:
            FINE_RATE_PER_DAY = 1.00 # Example: $1.00 per day
            fine_amount_calculated = overdue_days * FINE_RATE_PER_DAY
            loan.fine_amount = fine_amount_calculated
    else:
        loan.status = 'RETURNED'
        loan.fine_amount = 0

    loan.save()

    book_copy_instance.status = 'Available'
    book_copy_instance.save(update_fields=['status'])

    # Create Notification
    return_message = _(f"Book '{book_copy_instance.book.title}' (Copy: {book_copy_instance.copy_id}) has been successfully returned.")
    notification_type = 'RETURN_CONFIRMED'
    if loan.status == 'RETURNED_LATE' and fine_amount_calculated > 0:
        fine_message = _(f" A fine of ${fine_amount_calculated:.2f} has been applied for late return.")
        return_message += fine_message
        notification_type = 'FINE_ISSUED' # Or have a separate notification for fines

    Notification.objects.create(
        recipient=loan.borrower,
        notification_type=notification_type,
        message=return_message
    )
    messages.success(request, return_message)
    
    return redirect('books:dashboard_active_loans')



class StaffActiveLoansView(StaffRequiredMixin, ListView):
    """
    Displays a list of all currently active and overdue loans.
    Ordered by due date to prioritize those due soonest or already overdue.
    """
    model = Borrowing
    template_name = 'books/dashboard/circulation/active_loans.html' # You've created this empty file
    context_object_name = 'active_loans'
    paginate_by = 10

    def get_queryset(self):
        queryset = Borrowing.objects.filter(status__in=['ACTIVE', 'OVERDUE']) \
                                    .select_related('borrower', 'book_copy__book') \
                                    .order_by('due_date') # Show soonest due/most overdue first

        search_term = self.request.GET.get('search', '').strip()
        # Optional: Filter by 'OVERDUE' status explicitly if needed via a dropdown
        # status_filter = self.request.GET.get('status_filter', '').strip()

        if search_term:
            queryset = queryset.filter(
                Q(borrower__username__icontains=search_term) |
                Q(borrower__first_name__icontains=search_term) |
                Q(borrower__last_name__icontains=search_term) |
                Q(book_copy__book__title__icontains=search_term) |
                Q(book_copy__copy_id__icontains=search_term) |
                Q(book_copy__book__isbn__icontains=search_term)
            )
        # if status_filter == 'OVERDUE':
        #     queryset = queryset.filter(status='OVERDUE', due_date__date__lt=timezone.now().date())
        # elif status_filter == 'ACTIVE_NOT_OVERDUE':
        #     queryset = queryset.filter(status='ACTIVE', due_date__date__gte=timezone.now().date())
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Active & Overdue Loans')
        context['now_date'] = timezone.now().date() # For easy overdue comparison in template
        context['current_search'] = self.request.GET.get('search', '')
        # context['current_status_filter'] = self.request.GET.get('status_filter', '')
        
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['other_query_params'] = query_params.urlencode()
        return context

@login_required
@user_passes_test(is_staff_user)
def staff_mark_loan_returned_view(request, borrowing_id):
    """Staff action to mark an active/overdue loan as returned."""
    loan = get_object_or_404(Borrowing, id=borrowing_id, status__in=['ACTIVE', 'OVERDUE'])
    book_copy = loan.book_copy

    loan.return_date = timezone.now()
    loan.status = 'RETURNED_LATE' if loan.due_date < timezone.now().date() else 'RETURNED'
    # TODO: Implement actual fine calculation based on library policy
    # if loan.status == 'RETURNED_LATE':
    #     overdue_duration = timezone.now() - loan.due_date
    #     loan.fine_amount = calculate_fine(overdue_duration) # Implement calculate_fine
    loan.save()

    book_copy.status = 'Available'
    book_copy.save()
    Notification.objects.create(
        recipient=loan.borrower,
        notification_type='RETURN_CONFIRMED',
        message=f"Your loan for '{book_copy.book.title}' has been processed as returned."
    )
    messages.success(request, _(f"Loan for '{book_copy.book.title}' marked as returned."))
    return redirect('books:dashboard_active_loans')

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

