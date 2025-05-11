from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.urls import reverse_lazy
from datetime import datetime, timedelta

# DRF Imports
from rest_framework import viewsets, permissions, status, generics, serializers
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend

# App-specific imports
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
    return user.is_authenticated and (user.role in ['LIBRARIAN', 'ADMIN'] or user.is_staff)

def is_admin_user(user):
    return user.is_authenticated and (user.role == 'ADMIN' or user.is_staff)


# --- DRF Permission Classes ---
class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated and \
               (request.user.role == 'ADMIN' or request.user.is_staff)

class IsLibrarianOrAdminPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and \
               (request.user.role in ['LIBRARIAN', 'ADMIN'] or request.user.is_staff)


# --- DRF ViewSets ---
class AuthorViewSet(viewsets.ModelViewSet):
    queryset = Author.objects.all().order_by('name')
    serializer_class = AuthorSerializer
    permission_classes = [IsAdminOrReadOnly] 
    filter_backends = [DjangoFilterBackend, permissions.SearchFilter, permissions.OrderingFilter]
    search_fields = ['name', 'biography']
    ordering_fields = ['name', 'date_of_birth']
    filterset_fields = ['name']


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, permissions.SearchFilter, permissions.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name']
    filterset_fields = ['name']


class BookViewSet(viewsets.ModelViewSet):
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
        book = self.get_object()
        available_copies = book.copies.filter(status='Available')
        serializer = BookCopySerializer(available_copies, many=True, context={'request': request})
        return Response(serializer.data)

class BookCopyViewSet(viewsets.ModelViewSet):
    queryset = BookCopy.objects.all().select_related('book').order_by('book__title', 'copy_id')
    permission_classes = [IsLibrarianOrAdminPermission]
    filter_backends = [DjangoFilterBackend, permissions.SearchFilter, permissions.OrderingFilter]
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
        user = self.request.user
        if user.role in ['LIBRARIAN', 'ADMIN'] or user.is_staff:
            return Borrowing.objects.all().select_related('borrower', 'book_copy__book')
        elif user.role == 'BORROWER':
            return Borrowing.objects.filter(borrower=user).select_related('borrower', 'book_copy__book')
        return Borrowing.objects.none()

    def perform_create(self, serializer):
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

        due_date = timezone.now() + timedelta(days=14)
        instance = serializer.save(borrower=borrower, due_date=due_date, status='ACTIVE')
        book_copy_instance.status = 'On Loan'
        book_copy_instance.save(update_fields=['status'])

        Notification.objects.create(
            recipient=borrower,
            notification_type='BORROW_APPROVED',
            message=_(f"The book '{book_copy_instance.book.title}' (Copy ID: {book_copy_instance.copy_id}) has been issued to you. Due date: {due_date.strftime('%Y-%m-%d')}.")
        )

    @action(detail=True, methods=['post'], permission_classes=[IsLibrarianOrAdminPermission], url_path='return-book')
    def return_book(self, request, pk=None):
        borrowing_record = self.get_object()
        if borrowing_record.status not in ['ACTIVE', 'OVERDUE']:
            return Response(
                {'error': _('This book loan is not currently active or overdue. It might have already been returned or cancelled.')}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        borrowing_record.actual_return_date = timezone.now()
        book_copy_instance = borrowing_record.book_copy
        
        book_copy_instance.status = 'Available'
        book_copy_instance.save(update_fields=['status'])

        if borrowing_record.due_date < borrowing_record.actual_return_date:
            borrowing_record.status = 'RETURNED_LATE'
            overdue_days = (borrowing_record.actual_return_date.date() - borrowing_record.due_date.date()).days
            if overdue_days > 0:
                borrowing_record.fine_amount = overdue_days * 1.00 
        else:
            borrowing_record.status = 'RETURNED'
        
        borrowing_record.save()
        
        Notification.objects.create(
            recipient=borrowing_record.borrower,
            notification_type='RETURN_CONFIRMED',
            message=_(f"Your loan for '{book_copy_instance.book.title}' (Copy ID: {book_copy_instance.copy_id}) has been returned.")
        )
        
        return Response(BorrowingSerializer(borrowing_record, context={'request': request}).data)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, permissions.OrderingFilter]
    filterset_fields = ['notification_type', 'is_read']
    ordering_fields = ['timestamp', 'notification_type']
    ordering = ['-timestamp']

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_as_read(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'detail': _('All notifications marked as read.')}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        return Response(NotificationSerializer(notification, context={'request': request}).data)


# --- Django Template-Rendering Views (Borrower Web Portal & Staff Dashboard) ---
class BookPortalListView(ListView):
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
    selected_category = None
    if category_id:
        selected_category = get_object_or_404(Category, id=category_id)
    elif category_slug:
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


@login_required
@user_passes_test(is_librarian_or_admin_user, login_url=reverse_lazy('users:login'))
def staff_dashboard_home(request):
    context = {
        'page_title': _("Staff Dashboard"),
        'book_title_count': Book.objects.count(),
        'book_copy_count': BookCopy.objects.count(),
        'active_loans_count': Borrowing.objects.filter(status='ACTIVE').count(),
        'overdue_loans_count': Borrowing.objects.filter(status='OVERDUE').count(),
        'total_borrowers_count': CustomUser.objects.filter(role='BORROWER').count(),
    }
    return render(request, 'dashboard/staff_home.html', context)


# --- Old Template Views (Bottom Section - Targeted Fixes Applied) ---
@members_only
def books_list_view(request):
    search = request.GET.get("search", "")
    books = Book.objects.all().order_by('title')
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


# --- Helper Function for Old Dashboard Views ---
def _get_dashboard_context(request, active_tab_name, queryset, search_fields=None):
    search = request.GET.get('search', '').strip()
    if search and search_fields:
        query = Q()
        for field in search_fields:
            if field == 'borrower__username':
                query |= Q(borrower__username__icontains=search)
            elif field == 'book_copy__book__title':
                query |= Q(book_copy__book__title__icontains=search)
            elif field == 'authors__name':
                 query |= Q(authors__name__icontains=search)
            elif field == 'categories__name':
                 query |= Q(categories__name__icontains=search)
            else:
                query |= Q(**{f'{field}__icontains': search})
        
        if queryset.model == Book and ('authors__name' in search_fields or 'categories__name' in search_fields):
             queryset = queryset.filter(query).distinct()
        else:
             queryset = queryset.filter(query)

    if queryset.model == Borrowing:
        if active_tab_name == 'pending': 
            queryset = queryset.order_by('issue_date') 
        elif active_tab_name == 'active':
            queryset = queryset.order_by('due_date') 
        elif active_tab_name == 'history':
             queryset = queryset.order_by('-actual_return_date', '-issue_date') # Order by return date then issue date
    elif queryset.model == Book:
        queryset = queryset.order_by('title')
    # elif queryset.model == CustomUser: # Example for user ordering
    #      queryset = queryset.order_by('last_name', 'first_name')

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'active_dashboard_tab': active_tab_name,
        'page_obj': page_obj,
        'search_term': search,
        'now': timezone.now(),
    }
    return context

@admin_only
def librarian_dashboard_view(request):
    return redirect('books:dashboard_pending_v1')

@admin_only
def dashboard_pending_view(request):
    active_tab_name = 'pending'
    pending_qs = Borrowing.objects.filter(status='REQUESTED').select_related('book_copy__book', 'borrower')
    context = _get_dashboard_context(
        request, active_tab_name, pending_qs,
        search_fields=['book_copy__book__title', 'borrower__username']
    )
    return render(request, 'dashboard/pending_section.html', context)

@admin_only
def dashboard_active_view(request):
    active_tab_name = 'active'
    active_qs = Borrowing.objects.filter(status='ACTIVE').select_related('book_copy__book', 'borrower')
    context = _get_dashboard_context(
        request, active_tab_name, active_qs,
        search_fields=['book_copy__book__title', 'borrower__username']
    )
    return render(request, 'dashboard/active_section.html', context)

@admin_only
def dashboard_history_view(request):
    active_tab_name = 'history'
    history_qs = Borrowing.objects.filter(status__in=['RETURNED', 'RETURNED_LATE', 'CANCELLED', 'LOST_BY_BORROWER']).select_related('book_copy__book', 'borrower')
    context = _get_dashboard_context(
        request, active_tab_name, history_qs,
        search_fields=['book_copy__book__title', 'borrower__username']
    )
    return render(request, 'dashboard/history_section.html', context)

@admin_only
def dashboard_books_view(request):
    active_tab_name = 'books'
    book_qs = Book.objects.all().prefetch_related('authors', 'categories')
    context = _get_dashboard_context(
        request, active_tab_name, book_qs,
        search_fields=['title', 'authors__name', 'categories__name', 'isbn']
    )
    return render(request, 'dashboard/books_section.html', context)


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
        cover_image_url_val = request.POST.get('cover_image_url', '').strip()

        authors_raw = request.POST.get('authors', '').strip() 
        categories_raw = request.POST.get('categories', '').strip()

        if not title or not isbn_val:
            messages.error(request, _("Book title and ISBN are required."))
            return redirect('books:dashboard_books_v1')
        
        if Book.objects.filter(isbn=isbn_val).exists():
            messages.error(request, _(f"A book with ISBN {isbn_val} already exists."))
            return redirect('books:dashboard_books_v1')

        try:
            initial_copies = int(initial_copies_str)
            if initial_copies < 0: raise ValueError(_("Number of copies cannot be negative."))
        except (ValueError, TypeError):
            messages.error(request, _("Invalid number of initial copies provided."))
            return redirect('books:dashboard_books_v1')
        
        page_count = None
        if page_count_str:
            try:
                page_count = int(page_count_str)
                if page_count <= 0: raise ValueError(_("Page count must be positive."))
            except (ValueError, TypeError):
                messages.error(request, _("Invalid page count provided. Must be a number."))
                return redirect('books:dashboard_books_v1')

        publish_date = None
        if publish_date_str:
            try:
                publish_date = datetime.strptime(publish_date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, _("Invalid publish date format. Use YYYY-MM-DD."))
                return redirect('books:dashboard_books_v1')

        book = Book.objects.create(
            isbn=isbn_val, title=title, description=summary or None,
            publisher=publisher or None, publication_date=publish_date,
            page_count=page_count, cover_image_url=cover_image_url_val or None
        )

        author_ids = []
        for name in [n.strip() for n in authors_raw.split(',') if n.strip()]:
            author, _ = Author.objects.get_or_create(name=name)
            author_ids.append(author.id)
        if author_ids: book.authors.set(author_ids) 

        category_ids_list = []
        for name in [n.strip() for n in categories_raw.split(',') if n.strip()]:
            category_obj, _ = Category.objects.get_or_create(name=name)
            category_ids_list.append(category_obj.id)
        if category_ids_list: book.categories.set(category_ids_list)

        for _ in range(initial_copies):
            copy_id_val = f"{book.isbn}-C{BookCopy.objects.filter(book=book).count() + 1}"
            BookCopy.objects.create(book=book, copy_id=copy_id_val, status='Available')

        messages.success(request, _(f"Book '{book.title}' and {initial_copies} cop(y/ies) added successfully."))
    except Exception as e:
         messages.error(request, _(f"Error adding book: {e}"))
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
        book.cover_image_url = request.POST.get('cover_image_url', book.cover_image_url).strip() or None
        
        authors_raw = request.POST.get('authors', '').strip() 
        categories_raw = request.POST.get('categories', '').strip()

        if not book.title:
            messages.error(request, _("Book title cannot be empty."))
            return redirect('books:dashboard_books_v1')

        if page_count_str:
            try:
                book.page_count = int(page_count_str)
                if book.page_count <= 0: raise ValueError(_("Page count must be positive."))
            except (ValueError, TypeError):
                messages.error(request, _("Invalid page count provided."))
                return redirect('books:dashboard_books_v1')
        else:
             book.page_count = None 

        if publish_date_str:
            try:
                book.publication_date = datetime.strptime(publish_date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, _("Invalid publish date format. Use YYYY-MM-DD."))
                return redirect('books:dashboard_books_v1')
        else:
             book.publication_date = None

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
        messages.success(request, _(f"Book '{book.title}' updated successfully."))
    except Exception as e:
         messages.error(request, _(f"Error updating book: {e}"))
    return redirect('books:dashboard_books_v1')


@staff_member_required
@require_POST
def delete_book_view(request, book_isbn):
    book = get_object_or_404(Book, isbn=book_isbn)
    if Borrowing.objects.filter(book_copy__book=book, status__in=['ACTIVE', 'OVERDUE', 'REQUESTED']).exists():
        messages.error(request, _(f"Cannot delete '{book.title}' as one or more of its copies are currently involved in active or pending loans."))
        return redirect('books:dashboard_books_v1')
    
    book_title_for_message = book.title
    book.delete()
    messages.success(request, _(f"Book '{book_title_for_message}' and all its copies deleted successfully."))
    return redirect('books:dashboard_books_v1')
