from django.conf import settings
from django.db import models
from django.utils import timezone

class Author(models.Model):
    name = models.CharField(max_length=255, unique=True)
    bio = models.TextField(blank=True)

    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']

class Genre(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']

class Book(models.Model):
    # Core Information
    title = models.CharField(max_length=255)
    authors = models.ManyToManyField(Author, related_name='books') 
    genres = models.ManyToManyField(Genre, blank=True, related_name='books') 
    summary = models.TextField(blank=True) 
    cover_image = models.ImageField(upload_to='book_covers/', blank=True, null=True)

    # Inventory & Usage
    quantity = models.PositiveIntegerField(default=1) 
    total_borrows = models.PositiveIntegerField(default=0) 

    # User Interaction
    favorited_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='favorite_books',
        blank=True
    )

    # Other Information
    publisher = models.CharField(max_length=255, blank=True, null=True)
    publish_date = models.DateField(blank=True, null=True) 
    isbn_13 = models.CharField('ISBN-13', max_length=17, blank=True, null=True, unique=True) 
    isbn_10 = models.CharField('ISBN-10', max_length=13, blank=True, null=True, unique=True) 
    language = models.CharField(max_length=50, blank=True, null=True)
    page_count = models.PositiveIntegerField(blank=True, null=True)
    open_library_id = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return self.title

    @property
    def is_available(self):
        """Checks if any copies are currently available for borrowing."""
        # This needs a more accurate calculation based on active borrowings
        return self.quantity > 0 # Placeholder logic
    
        # TODO: Implement accurate availability check (quantity - active borrowings)
        # active_borrow_count = self.borrowings.filter(status='approved', actual_return_date__isnull=True).count()
        # return self.quantity > active_borrow_count

    class Meta:
        ordering = ['title']

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    message = models.TextField()
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    NOTIFICATION_TYPES = [('approval', 'Approval'), ('reminder', 'Reminder'), ('overdue', 'Overdue')]
    type = models.CharField(max_length=10, choices=NOTIFICATION_TYPES, default='approval')

    def __str__(self):
        return f"Notification for {self.user.username}: {self.title}"

    class Meta:
        ordering = ['-created_at']

class Borrowing(models.Model):
    """
    Represents a borrowing record for a book by a user.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('returned', 'Returned'),
        ('rejected', 'Rejected'),
        # Optional: ('overdue', 'Overdue') # Could be set by a scheduled task
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='borrowings'
    )
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='borrowings'
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )

    borrow_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(null=True, blank=True)
    actual_return_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        due_date_str = self.due_date.strftime('%Y-%m-%d') if self.due_date else 'N/A'
        return f"{self.user.username} → {self.book.title} (Due: {due_date_str}, Status: {self.status})"

    @property
    def is_overdue(self):
        """
        Checks if the borrowing record is currently overdue.
        Only relevant if the status indicates it's currently borrowed ('approved').
        """
        return (
            self.status == 'approved' and
            self.due_date and
            self.actual_return_date is None and
            timezone.now() > self.due_date
        )

    class Meta:
        ordering = ['-borrow_date']

