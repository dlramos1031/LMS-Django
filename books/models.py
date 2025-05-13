from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator

from django.utils import timezone

isbn_validator = RegexValidator(
    regex=r'^(?:ISBN(?:-13)?:?)(?=[0-9]{13}$|(?=(?:[0-9]+[- ]){4})[- 0-9]{17}$)97[89][- ]?[0-9]{1,5}[- ]?[0-9]+[- ]?[0-9]+[- ]?[0-9]$',
    message=_("Enter a valid ISBN-13. It must start with 978 or 979 and be 13 digits long (hyphens optional).")
)


class Author(models.Model):
    """
    Represents an author of a book.
    Each author can write multiple books, and each book can have multiple authors (ManyToManyField in Book model).
    """
    name = models.CharField(
        max_length=200, 
        help_text=_("Enter the author's full name (e.g., J.R.R. Tolkien)")
    )
    biography = models.TextField(
        blank=True, 
        null=True, 
        help_text=_("A short biography of the author (optional)")
    )
    date_of_birth = models.DateField(
        _("Date of Birth"), # Changed to use verbose_name directly
        null=True, 
        blank=True,
        help_text=_("Author's date of birth (optional)")
    )
    date_of_death = models.DateField(
        _("Date of Death"),
        null=True,
        blank=True,
        help_text=_("Author's date of death, if applicable (optional)")
    )
    nationality = models.CharField(
        _("Nationality"),
        max_length=100,
        blank=True,
        null=True,
        help_text=_("Author's nationality (e.g., British, American) (optional)")
    )
    alternate_names = models.CharField(
        _("Alternate Names"),
        max_length=500, # Increased length for potentially multiple names
        blank=True,
        null=True,
        help_text=_("Other names the author is known by, separated by commas (e.g., pen names, maiden names) (optional)")
    )
    author_website = models.URLField(
        _("Author Website"),
        blank=True,
        null=True,
        help_text=_("A link to the author's official website or a relevant resource page (optional)")
    )
    author_photo = models.ImageField(
        _("Author Photo"),
        upload_to='author_photos/',
        blank=True,
        null=True,
        help_text=_("A photo of the author (optional).")
    )

    def __str__(self):
        """String representation of the Author model, used in Django admin and debugging."""
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = _('Author')
        verbose_name_plural = _('Authors')

    def get_life_span(self):
        if self.date_of_birth:
            birth_year = self.date_of_birth.year
            if self.date_of_death:
                death_year = self.date_of_death.year
                return f"{birth_year}–{death_year}"
            return f"Born {birth_year}"
        return "N/A"
    get_life_span.short_description = _('Life Span')


class Category(models.Model):
    """
    Represents a book category (e.g., Fiction, Science, History).
    Books can belong to multiple categories, and categories can contain multiple books (ManyToManyField in Book model).
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_("Enter a book category (e.g., Science Fiction, Programming, History)")
    )
    description = models.TextField(
        blank=True, 
        null=True,
        help_text=_("A short description of the category (optional)")
    )
    # Optional: Hierarchical categories (e.g., Fiction -> Fantasy)
    # parent_category = models.ForeignKey('self', null=True, blank=True, related_name='subcategories', on_delete=models.SET_NULL)

    def __str__(self):
        """String representation of the Category model."""
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = _('Category')
        verbose_name_plural = _('Categories')


class Book(models.Model):
    """
    Represents a book title or edition (the abstract concept of a book, not a specific physical copy).
    Specific physical copies are handled by the BookCopy model.
    """

    isbn = models.CharField(
        _('ISBN-13'),
        max_length=17,
        primary_key=True,
        unique=True,
        validators=[isbn_validator],
        help_text=_('13 Character ISBN number. Must be unique. (e.g., 978-0596009205)')
    )
    title = models.CharField(
        max_length=255,
        help_text=_("Enter the title of the book")
    )
    authors = models.ManyToManyField(
        Author, 
        related_name='books',
        help_text=_("Select or add authors for this book")
    )
    publisher = models.CharField(
        max_length=200, 
        blank=True, 
        null=True,
        help_text=_("Publisher of the book (optional)")
    )
    publication_date = models.DateField(
        null=True, 
        blank=True,
        help_text=_("Date the book was published (optional)")
    )
    edition = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text=_("e.g., 1st Edition, Revised Edition (optional)")
    )
    page_count = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text=_("Total number of pages (optional)")
    )
    description = models.TextField(
        blank=True, 
        null=True,
        help_text=_("A brief description or summary of the book (optional)")
    )
    cover_image = models.ImageField(
        _("Cover Image"),
        upload_to='book_covers/',
        blank=True,
        null=True,
        help_text=_("Upload the book's cover image (optional).")
    )
    categories = models.ManyToManyField(
        Category,
        related_name='books',
        help_text=_("Select or add categories for this book")
    )
    
    date_added_to_system = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Date this book record was added to the system")
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        help_text=_("Date this book record was last updated")
    )

    total_borrows = models.PositiveIntegerField(
        default=0, 
        help_text=_("How many times this book title has been borrowed overall")
    )

    def __str__(self):
        """String representation of the Book model."""
        return f"{self.title} (ISBN: {self.isbn})"

    def display_authors(self):
        """Helper method to display authors in the Django admin interface."""
        return ', '.join(author.name for author in self.authors.all()[:3])
    display_authors.short_description = _('Authors')

    def display_categories(self):
        """Helper method to display categories in the Django admin interface."""
        return ', '.join(category.name for category in self.categories.all()[:3])
    display_categories.short_description = _('Categories')
    
    @property
    def available_copies_count(self):
        """Returns the number of currently 'Available' physical copies for this book title."""
        return self.copies.filter(status='Available').count()

    class Meta:
        ordering = ['title', 'isbn']
        verbose_name = _('Book')
        verbose_name_plural = _('Books')


class BookCopy(models.Model):
    """
    Represents a specific, physical copy of a Book.
    If the library has 5 copies of "The Hobbit", there will be one Book record for "The Hobbit"
    and five BookCopy records linked to it.
    """
    book = models.ForeignKey(
        Book, 
        on_delete=models.CASCADE,
        related_name='copies',
        help_text=_("The book title this specific copy belongs to")
    )
    copy_id = models.CharField(
        max_length=100,
        unique=True,
        help_text=_("Unique library barcode or identifier for this specific physical copy")
    )
    
    STATUS_CHOICES = [
        ('Available', _('Available')),
        ('On Loan', _('On Loan')),
        ('Reserved', _('Reserved')),
        ('Lost', _('Lost')),
        ('Damaged', _('Damaged')),
        ('In Repair', _('In Repair')),
        ('Withdrawn', _('Withdrawn from Collection')),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Available',
        help_text=_("Current status of this book copy")
    )
    date_acquired = models.DateField(
        null=True, 
        blank=True,
        help_text=_("Date this specific copy was acquired by the library (optional)")
    )
    condition_notes = models.TextField(
        blank=True, 
        null=True,
        help_text=_("Notes on the condition of this copy (e.g., slight tear on cover, missing page) (optional)")
    )
    # Optional: 'location_in_library' field (e.g., "Shelf A-3")

    def __str__(self):
        """String representation of the BookCopy model."""
        return f"{self.book.title} (Copy ID: {self.copy_id}) - Status: {self.get_status_display()}"

    class Meta:
        ordering = ['book__title', 'copy_id']
        verbose_name = _('Book Copy')
        verbose_name_plural = _('Book Copies')


class Borrowing(models.Model):
    """
    Represents a borrowing transaction: a specific BookCopy loaned to a specific Borrower.
    """
    book_copy = models.ForeignKey(
        BookCopy, 
        on_delete=models.PROTECT,
        related_name='borrowings', 
        help_text=_("The specific copy of the book being borrowed")
    )
    borrower = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='borrowings', 
        help_text=_("The user borrowing the book")
    )
    request_date = models.DateTimeField(
        verbose_name=_("Request Date"),
        auto_now_add=True,
        help_text=_("Date and time the borrow request was made or manual issue initiated.")
    )
    issue_date = models.DateTimeField(
        verbose_name=_("Issue Date"),
        null=True, blank=True,
        help_text=_("Date and time the loan was approved and officially started.")
    )
    due_date = models.DateField(
        verbose_name=_("Due Date"),
        help_text=_("Date the book is due to be returned. Set by user/staff during request/approval.")
    )
    return_date = models.DateTimeField(
        verbose_name=_("Actual Return Date"),
        null=True, blank=True,
        help_text=_("Date and time the book was actually returned.")
    )
    STATUS_CHOICES = [
        ('REQUESTED', _('Requested')),                  # Book is requested before librarian approval
        ('ACTIVE', _('Active')),                        # Book is currently borrowed by the user
        ('RETURNED', _('Returned')),                    # Book has been returned on or before the due date
        ('RETURNED_LATE', _('Returned Late')),          # Book returned after the due date
        ('OVERDUE', _('Overdue')),                      # Book not yet returned and is past its due date
        ('REJECTED', _('Request Rejected')),            # Borrow request was rejected by librarian
        ('CANCELLED', _('Request Cancelled')),          # If a borrow request was cancelled before approval
        ('LOST_BY_BORROWER', _('Lost by Borrower')),    # Borrower reported or confirmed the book as lost
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='REQUESTED',
        help_text=_("Current status of this borrowing record")
    )
    fine_amount = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0.00,
        help_text=_("Fine incurred for this borrowing, if any (e.g., for late return)")
    )
    notes_by_librarian = models.TextField(
        blank=True,
        null=True,
        help_text=_("Internal notes by librarian regarding this loan (e.g., damage noted on return) (optional)")
    )

    def __str__(self):
        """String representation of the Borrowing model."""
        return f"{self.borrower.username} borrowed '{self.book_copy.book.title}' (Copy: {self.book_copy.copy_id})"

    def save(self, *args, **kwargs):
        """
        Custom save method.
        Example: Increment total_borrows on the Book when a borrowing record is first created and active.
        This could also be handled more robustly with Django Signals for better decoupling.
        """
        is_new_active_loan = False
        if self._state.adding and self.status == 'ACTIVE':
            is_new_active_loan = True
        elif not self._state.adding:
            try:
                old_instance = Borrowing.objects.get(pk=self.pk)
                if old_instance.status != 'ACTIVE' and self.status == 'ACTIVE':
                    is_new_active_loan = True
            except Borrowing.DoesNotExist:
                if self.status == 'ACTIVE':
                    is_new_active_loan = True
        
        super().save(*args, **kwargs)

        if is_new_active_loan:
            book_title = self.book_copy.book
            Book.objects.filter(pk=book_title.pk).update(total_borrows=models.F('total_borrows') + 1)

    class Meta:
        ordering = ['-request_date']
        verbose_name = _('Borrowing Record')
        verbose_name_plural = _('Borrowing Records')


class Notification(models.Model):
    """
    Model to store notifications for users (borrowers or staff).
    """
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='notifications',
        help_text=_("The user who will receive this notification")
    )
    
    NOTIFICATION_TYPE_CHOICES = [
        ('BORROW_APPROVED', _('Borrow Request Approved')),
        ('BORROW_REJECTED', _('Borrow Request Rejected')),
        ('RESERVATION_AVAILABLE', _('Reservation Available')),  # When a reserved book is ready for pickup
        ('DUE_REMINDER', _('Due Date Reminder')),               # Sent a few days before a book is due
        ('OVERDUE_ALERT', _('Book Overdue Alert')),             # Sent when a book becomes overdue
        ('RETURN_CONFIRMED', _('Book Return Confirmed')),       # Confirmation after a book is returned
        ('FINE_ISSUED', _('Fine Issued')),                      # Notification about a new fine
        ('GENERAL_ANNOUNCEMENT', _('General Announcement')),    # For library-wide messages
    ]
    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPE_CHOICES,
        help_text=_("The type or category of the notification")
    )
    message = models.TextField(
        help_text=_("The content of the notification message")
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text=_("Date and time the notification was created")
    )
    is_read = models.BooleanField(
        default=False,
        help_text=_("Indicates whether the recipient has read the notification")
    )
    
    # Optional: Link to a relevant object that the notification is about
    # This uses Django's generic relations if the related object can be of different types (e.g., a Borrowing record, a Book).
    # from django.contrib.contenttypes.fields import GenericForeignKey
    # from django.contrib.contenttypes.models import ContentType
    # content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    # object_id = models.PositiveIntegerField(null=True, blank=True)
    # related_object = GenericForeignKey('content_type', 'object_id')

    def __str__(self):
        """String representation of the Notification model."""
        return f"Notification for {self.recipient.username}: {self.get_notification_type_display()} ({'Read' if self.is_read else 'Unread'})"

    class Meta:
        ordering = ['-timestamp']
        verbose_name = _('Notification')
        verbose_name_plural = _('Notifications')

