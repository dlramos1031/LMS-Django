from rest_framework import serializers
from .models import Author, Book, Genre, Borrowing, Notification
from django.utils import timezone

class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ['id', 'name']

class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ['id', 'name']

class BookSerializer(serializers.ModelSerializer):
    """Serializer for Book model, including detailed fields."""
    authors = AuthorSerializer(many=True, read_only=True)
    genres = GenreSerializer(many=True, read_only=True)

    author_ids = serializers.PrimaryKeyRelatedField(
        queryset=Author.objects.all(),
        many=True,
        write_only=True, 
        source='authors', 
        required=False 
    )
    genre_ids = serializers.PrimaryKeyRelatedField(
        queryset=Genre.objects.all(),
        many=True,
        write_only=True, 
        source='genres', 
        required=False 
    )

    is_available = serializers.ReadOnlyField() 
    is_favorite = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            'id', 'title', 'summary', 'cover_image',
            'quantity', 'is_available', 'total_borrows',
            'authors', 'genres', 
            'publisher', 'publish_date', 'isbn_13', 'isbn_10',
            'language', 'page_count', 'open_library_id',
            'is_favorite', 
            'author_ids', 'genre_ids',
        ]
        read_only_fields = ['is_available', 'is_favorite', 'total_borrows']

    def get_is_favorite(self, obj):
        """Check if the book is favorited by the current request user."""
        request = self.context.get('request', None)
        if request and request.user.is_authenticated:
            return obj.favorited_by.filter(pk=request.user.pk).exists()
        return False

    def validate_page_count(self, value):
        """Ensure page count is positive if provided."""
        if value is not None and value <= 0:
            raise serializers.ValidationError("Page count must be a positive number.")
        return value

    def validate_publish_date(self, value):
        """Ensure publish date is not in the future if provided."""
        if value is not None and value > timezone.localdate():
             raise serializers.ValidationError("Publish date cannot be in the future.")
        return value

class BorrowingSerializer(serializers.ModelSerializer):
    """
    Serializer for the Borrowing model, reflecting refactored fields.
    """
    book = BookSerializer(read_only=True)
    is_overdue = serializers.ReadOnlyField()

    class Meta:
        model = Borrowing
        fields = [
            'id',
            'book',
            'borrow_date',
            'due_date', 
            'actual_return_date', 
            'status',
            'is_overdue', 
        ]
        read_only_fields = [
            'id',
            'book', 
            'borrow_date',
            'actual_return_date',
            'status', 
            'is_overdue',
        ]

class NotificationSerializer(serializers.ModelSerializer):
    """
    Serializer for Notification model (remains mostly the same).
    """
    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'read', 'created_at']
        read_only_fields = ['id', 'title', 'message', 'created_at']  