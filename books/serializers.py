from rest_framework import serializers
from .models import Author, Book, Genre, Borrowing, Notification
from django.utils import timezone

class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = '__all__'

class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ['id', 'name']

class BookSerializer(serializers.ModelSerializer):
    authors = AuthorSerializer(many=True, read_only=True)
    author_ids = serializers.PrimaryKeyRelatedField(
        queryset=Author.objects.all(), many=True, write_only=True, source='authors'
    )
    genres = GenreSerializer(many=True, read_only=True)
    genre_ids = serializers.PrimaryKeyRelatedField(
        queryset=Genre.objects.all(), many=True, write_only=True, source='genres'
    )

    is_favorite = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            'id', 'title', 'summary', 'cover_image', 'open_library_id',
            'quantity', 'is_available', 'authors', 'author_ids',
            'genres', 'genre_ids', 'is_favorite'
        ]
        read_only_fields = ['is_available', 'is_favorite']
    
    def get_is_favorite(self, obj):
        user = self.context.get('request', None).user
        if user.is_authenticated:
            return obj.favorited_by.filter(pk=user.pk).exists()
        return False

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