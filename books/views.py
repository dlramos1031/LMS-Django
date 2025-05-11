from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, Count
from django.urls import reverse_lazy
from datetime import timedelta

# DRF Imports
from rest_framework import viewsets, permissions, status, generics, serializers, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend

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

# --- Staff Permission Helper ---
# This can be moved to a common 'decorators.py' or 'mixins.py' in a utility app or users app
# For now, keeping it here for self-containment based on previous discussions.
def is_staff_user(user):
    """Checks if the user is authenticated and has a staff-like role."""
    return user.is_authenticated and (user.role in ['LIBRARIAN', 'ADMIN'] or user.is_staff)

class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mixin to require staff privileges for accessing a view."""
    login_url = reverse_lazy('users:login')

    def test_func(self):
        return is_staff_user(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, _("You do not have permission to access this page."))
        if self.request.user.is_authenticated and not is_staff_user(self.request.user):
            return redirect('books:portal_catalog')
        return super().handle_no_permission()


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
        due_date_val = requested_due_date or (timezone.now() + timedelta(days=14))

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
        borrowing_record.actual_return_date = timezone.now()
        book_copy_instance = borrowing_record.book_copy
        book_copy_instance.status = 'Available'
        book_copy_instance.save(update_fields=['status'])

        if borrowing_record.due_date.date() < borrowing_record.actual_return_date.date():
            borrowing_record.status = 'RETURNED_LATE'
            overdue_days = (borrowing_record.actual_return_date.date() - borrowing_record.due_date.date()).days
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
            available_copies_count=Count('copies', filter=Q(copies__status='Available'))
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
    """Displays details for a single book for borrowers."""
    model = Book
    template_name = 'books/portal/book_detail.html'
    context_object_name = 'book'
    slug_field = 'isbn'
    slug_url_kwarg = 'isbn'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        book = self.get_object()
        context['page_title'] = book.title
        context['available_book_copies'] = book.copies.filter(status='Available')
        if self.request.user.is_authenticated:
            context['has_active_or_pending_request'] = Borrowing.objects.filter(
                borrower=self.request.user,
                book_copy__book=book, # Check against the book title
                status__in=['REQUESTED', 'ACTIVE']
            ).exists()
        # Consider adding related books logic here if needed
        return context

@login_required
def reserve_book_view(request, isbn): # Placeholder
    """Allows a logged-in user to request a reservation for a book."""
    book = get_object_or_404(Book, isbn=isbn)
    # TODO: Implement actual reservation logic
    # - Check if user already has this book reserved or an active loan.
    # - Check if the book is reservable (e.g., all copies are out).
    # - Create a Reservation record or update BookCopy status/queue.
    messages.info(request, _(f"Reservation feature for '{book.title}' is not yet implemented."))
    return redirect('books:portal_book_detail', isbn=isbn)

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
        'overdue_loans_count': Borrowing.objects.filter(status='OVERDUE', actual_return_date__isnull=True).count(),
        'total_borrowers_count': CustomUser.objects.filter(role='BORROWER').count(),
        'pending_requests_count': Borrowing.objects.filter(status='REQUESTED').count(),
    }
    return render(request, 'dashboard/home.html', context)

# --- Book & Collection Management (Staff) ---
class StaffBookListView(StaffRequiredMixin, ListView):
    """View for staff to list and manage book titles."""
    model = Book
    template_name = 'books/dashboard/book_management/book_list.html'
    context_object_name = 'books'
    paginate_by = 10

    def get_queryset(self):
        queryset = Book.objects.all().prefetch_related('authors', 'categories').annotate(
            copy_count=Count('copies'),
            available_copy_count=Count('copies', filter=Q(copies__status='Available'))
        ).order_by('title')
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Manage Book Titles')
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
        return reverse_lazy('books:dashboard_book_edit', kwargs={'isbn': self.book.isbn})

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
        return reverse_lazy('books:dashboard_book_edit', kwargs={'isbn': self.object.book.isbn})

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Manage Categories')
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
    form_class = AuthorForm
    template_name = 'books/dashboard/book_management/author_list.html'
    context_object_name = 'authors'
    paginate_by = 20
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Manage Authors')
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
    if not is_staff_user(request.user):
        messages.error(request, _("You do not have permission to access this page."))
        return redirect('books:portal_catalog')

    if request.method == 'POST':
        form = IssueBookForm(request.POST)
        if form.is_valid():
            borrower = form.cleaned_data['borrower']
            book_copy = form.cleaned_data['book_copy']
            due_date = form.cleaned_data['due_date']

            # Check again if book_copy is still available before creating borrowing record
            if book_copy.status == 'Available':
                Borrowing.objects.create(
                    borrower=borrower,
                    book_copy=book_copy,
                    due_date=due_date,
                    status='ACTIVE', # Staff issues directly to ACTIVE
                    # issued_by=request.user # Optional
                )
                book_copy.status = 'On Loan'
                book_copy.save()

                Notification.objects.create(
                    recipient=borrower,
                    notification_type='BORROW_APPROVED', # Or a general "Book Issued"
                    message=f"The book '{book_copy.book.title}' (Copy: {book_copy.copy_id}) has been issued to you. Due: {due_date.strftime('%Y-%m-%d')}."
                )
                messages.success(request, _(f"Book '{book_copy.book.title}' (Copy: {book_copy.copy_id}) issued to {borrower.username}."))
                return redirect('books:dashboard_active_loans')
            else:
                messages.error(request, _(f"Book copy '{book_copy.copy_id}' is no longer available. Current status: {book_copy.get_status_display()}"))
    else:
        form = IssueBookForm()

    context = {
        'form': form, 
        'page_title': _('Issue Book')
    }
    return render(request, 'books/dashboard/circulation/issue_book.html', context)

@login_required
@user_passes_test(is_staff_user)
def staff_return_book_view(request): # Placeholder - requires a form
    """Allows staff to mark a borrowed book copy as returned."""
    # form = ReturnBookForm(request.POST or None)
    # if request.method == 'POST' and form.is_valid():
    #     ... implement logic ...
    #     return redirect('books:dashboard_active_loans')
    # context = {'form': form, 'page_title': _('Return Book')}
    context = {'page_title': _('Return Book')} # Placeholder
    return render(request, 'books/dashboard/circulation/return_book.html', context)

class StaffPendingRequestsView(StaffRequiredMixin, ListView):
    """Displays borrow requests awaiting staff approval."""
    model = Borrowing
    template_name = 'books/dashboard/circulation/pending_requests.html'
    context_object_name = 'pending_requests'
    paginate_by = 10

    def get_queryset(self):
        return Borrowing.objects.filter(status='REQUESTED').select_related('borrower', 'book_copy__book').order_by('issue_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Pending Borrow Requests')
        return context

@login_required
@user_passes_test(is_staff_user)
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

@login_required
@user_passes_test(is_staff_user)
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
    """Displays all currently active and overdue loans."""
    model = Borrowing
    template_name = 'books/dashboard/circulation/active_loans.html'
    context_object_name = 'active_loans'
    paginate_by = 10

    def get_queryset(self):
        return Borrowing.objects.filter(status__in=['ACTIVE', 'OVERDUE']).select_related('borrower', 'book_copy__book').order_by('due_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Active & Overdue Loans')
        context['now_date'] = timezone.now().date()
        return context

@login_required
@user_passes_test(is_staff_user)
def staff_mark_loan_returned_view(request, borrowing_id):
    """Staff action to mark an active/overdue loan as returned."""
    loan = get_object_or_404(Borrowing, id=borrowing_id, status__in=['ACTIVE', 'OVERDUE'])
    book_copy = loan.book_copy

    loan.actual_return_date = timezone.now()
    loan.status = 'RETURNED_LATE' if loan.due_date.date() < timezone.now().date() else 'RETURNED'
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
    """Displays a history of all non-active borrowing records."""
    model = Borrowing
    template_name = 'books/dashboard/circulation/borrowing_history.html'
    context_object_name = 'borrowing_history'
    paginate_by = 15

    def get_queryset(self):
        return Borrowing.objects.filter(
            status__in=['RETURNED', 'RETURNED_LATE', 'REJECTED', 'CANCELLED', 'LOST_BY_BORROWER']
        ).select_related('borrower', 'book_copy__book').order_by('-actual_return_date', '-issue_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Borrowing History')
        return context

class StaffReservationListView(StaffRequiredMixin, TemplateView): # Or ListView for a Reservation model
    """Displays and manages book reservations (placeholder)."""
    template_name = 'books/dashboard/circulation/reservation_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = _('Manage Book Reservations')
        # TODO: Fetch actual reservation data
        # context['reservations'] = ...
        return context
