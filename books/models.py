from django.conf import settings
from django.db import models
from django.utils import timezone

class Author(models.Model):
    name = models.CharField(max_length=255)
    bio = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Genre(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name

class Book(models.Model):
    title = models.CharField(max_length=255)
    authors = models.ManyToManyField(Author)
    genres = models.ManyToManyField(Genre, blank=True)
    summary = models.TextField()
    cover_image = models.ImageField(upload_to='book_covers/', blank=True, null=True)
    open_library_id = models.CharField(max_length=50, blank=True, null=True)
    quantity = models.PositiveIntegerField(default=1)
    total_borrows = models.PositiveIntegerField(default=0)

    favorited_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name='favorite_books', 
        blank=True
    )

    def __str__(self):
        return self.title

    @property
    def is_available(self):
        return self.quantity > 0
    
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

