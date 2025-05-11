from django.contrib import admin
from .models import Author, Book, Category, BookCopy, Borrowing, Notification
from django.utils.translation import gettext_lazy as _

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ('name', 'date_of_birth')
    search_fields = ('name',)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

class BookCopyInline(admin.TabularInline):
    model = BookCopy
    extra = 1
    readonly_fields = ('copy_id',)
    fields = ('copy_id', 'status', 'date_acquired', 'condition_notes')


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'isbn', 'display_authors', 'display_categories', 'publication_date', 'total_borrows', 'available_copies_count')
    list_filter = ('categories', 'authors', 'publication_date')
    search_fields = ('title', 'isbn', 'authors__name', 'categories__name')
    filter_horizontal = ('authors', 'categories',)
    readonly_fields = ('date_added_to_system', 'last_updated', 'total_borrows')
    fieldsets = (
        (None, {
            'fields': ('title', 'isbn', 'authors', 'categories', 'description', 'cover_image_url')
        }),
        (_('Publication Info'), {
            'fields': ('publisher', 'publication_date', 'edition', 'page_count'),
            'classes': ('collapse',)
        }),
        (_('System Info'), {
            'fields': ('total_borrows', 'date_added_to_system', 'last_updated'),
            'classes': ('collapse',)
        }),
    )
    inlines = [BookCopyInline]


@admin.register(BookCopy)
class BookCopyAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'book', 'copy_id', 'status', 'date_acquired')
    list_filter = ('status', 'book__categories', 'date_acquired')
    search_fields = ('copy_id', 'book__title', 'book__isbn')
    autocomplete_fields = ['book']

@admin.register(Borrowing)
class BorrowingAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'borrower', 'book_copy', 'issue_date', 'due_date', 'actual_return_date', 'status', 'fine_amount')
    list_filter = ('status', 'issue_date', 'due_date', 'borrower')
    search_fields = ('borrower__username', 'book_copy__copy_id', 'book_copy__book__title')
    autocomplete_fields = ['borrower', 'book_copy']
    readonly_fields = ('issue_date',)
    fieldsets = (
        (None, {
            'fields': ('borrower', 'book_copy', 'due_date', 'status')
        }),
        (_('Return and Fine Details'), {
            'fields': ('actual_return_date', 'fine_amount', 'notes_by_librarian'),
            'classes': ('collapse',)
        }),
        (_('System Info (Read-Only)'), {
            'fields': ('issue_date',),
            'classes': ('collapse',)
        })
    )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notification_type', 'message_summary', 'timestamp', 'is_read')
    list_filter = ('notification_type', 'is_read', 'timestamp', 'recipient')
    search_fields = ('recipient__username', 'message')
    readonly_fields = ('timestamp',)

    def message_summary(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    message_summary.short_description = _('Message Summary')

