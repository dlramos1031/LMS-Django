from django.db import models

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

    def __str__(self):
        return self.title

    @property
    def is_available(self):
        return self.quantity > 0
