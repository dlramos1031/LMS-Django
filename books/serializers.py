from rest_framework import serializers
from .models import Author, Book, Category, BookCopy, Borrowing, Notification
from django.contrib.auth import get_user_model

CustomUser = get_user_model()


# Author & Category serializers

class AuthorSerializer(serializers.ModelSerializer):
    """
    Serializer for the Author model.
    Includes all relevant fields for author representation.
    """
    class Meta:
        model = Author
        fields = ['id', 'name', 'biography', 'date_of_birth']

class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer for the Category model (formerly Genre).
    """
    class Meta:
        model = Category
        fields = ['id', 'name', 'description']


# Book related serializers

class BookCopySerializer(serializers.ModelSerializer):
    """
    Serializer for individual BookCopy instances.
    Often used for listing copies or when a brief representation is needed.
    """
    class Meta:
        model = BookCopy
        fields = ['id', 'copy_id', 'status', 'book', 'date_acquired', 'condition_notes']

class BookMinimalSerializer(serializers.ModelSerializer):
    """
    A very minimal representation of a Book, often used in nested serializers
    to avoid too much data or circular dependencies.
    """
    class Meta:
        model = Book
        fields = ['isbn', 'title', 'cover_image_url']

class BookCopyDetailSerializer(serializers.ModelSerializer):
    """
    A more detailed serializer for BookCopy, which includes nested Book information.
    """
    book = BookMinimalSerializer(read_only=True)

    class Meta:
        model = BookCopy
        fields = ['id', 'copy_id', 'status', 'book', 'date_acquired', 'condition_notes']

class BookSerializer(serializers.ModelSerializer):
    """
    Serializer for the Book model.
    Handles read operations with nested author and category details.
    Handles write operations (create/update) using PrimaryKeyRelatedField for M2M relationships.
    """
    authors = AuthorSerializer(many=True, read_only=True)
    categories = CategorySerializer(many=True, read_only=True)
    
    author_ids = serializers.PrimaryKeyRelatedField(
        queryset=Author.objects.all(), 
        source='authors',
        many=True, 
        write_only=True,
        required=False
    )
    category_ids = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='categories',
        many=True, 
        write_only=True,
        required=False
    )
    
    available_copies_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Book
        fields = [
            'isbn', 'title', 
            'authors', 'author_ids',
            'publisher', 'publication_date', 'edition', 'page_count', 
            'description', 'cover_image_url', 
            'categories', 'category_ids',
            'total_borrows', 'date_added_to_system', 'last_updated',
            'available_copies_count'
        ]


# Borrowing related serializers

class BorrowerMinimalSerializer(serializers.ModelSerializer):
    """
    Minimal serializer for CustomUser, specifically for displaying borrower info
    in nested contexts like a borrowing record.
    """
    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'full_name', 'borrower_id_value']

class BorrowingSerializer(serializers.ModelSerializer):
    """
    Serializer for the Borrowing model.
    Includes nested details for the borrower and the specific book copy.
    """
    borrower = BorrowerMinimalSerializer(read_only=True)
    book_copy = BookCopyDetailSerializer(read_only=True)

    borrower_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.filter(role='BORROWER'),
        source='borrower', 
        write_only=True,
        required=False
    )
    book_copy_id = serializers.PrimaryKeyRelatedField(
        queryset=BookCopy.objects.all(), 
        source='book_copy', 
        write_only=True
    )

    class Meta:
        model = Borrowing
        fields = [
            'id', 
            'borrower', 'borrower_id', 
            'book_copy', 'book_copy_id', 
            'issue_date', 'due_date', 'return_date', 
            'status', 'fine_amount', 'notes_by_librarian'
        ]
        read_only_fields = ['issue_date', 'fine_amount']


# Notification related serializers

class NotificationSerializer(serializers.ModelSerializer):
    """
    Serializer for the Notification model.
    """

    class Meta:
        model = Notification
        fields = [
            'id', 'recipient',
            'notification_type', 'message', 
            'timestamp', 'is_read'
        ]
        read_only_fields = ['timestamp'] 