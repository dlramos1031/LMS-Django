from rest_framework import serializers
from .models import Author, Book, Category, BookCopy, Borrowing, Notification
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.utils import timezone
from django.conf import settings

CustomUser = get_user_model()


# Author & Category serializers

class AuthorSerializer(serializers.ModelSerializer):
    life_span = serializers.CharField(source='get_life_span', read_only=True) # Added for API if useful

    class Meta:
        model = Author
        fields = [
            'id', 'name', 'biography', 'date_of_birth', 'date_of_death',
            'nationality', 'alternate_names', 'author_website', 'author_photo',
            'life_span'
        ]

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
        fields = ['id', 'copy_id', 'status', 'book_id', 'date_acquired', 'condition_notes']

class BookMinimalSerializer(serializers.ModelSerializer):
    authors = AuthorSerializer(many=True, read_only=True)
    class Meta:
        model = Book
        fields = ['isbn', 'title', 'cover_image', 'authors']

class BookCopyDetailSerializer(serializers.ModelSerializer):
    """
    A more detailed serializer for BookCopy, which includes nested Book information.
    """
    book = serializers.StringRelatedField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    class Meta:
        model = BookCopy
        fields = [
            'id', 'copy_id', 'status', 'status_display', 'book', 
            'date_acquired', 'condition_notes'
        ]

class BookSerializer(serializers.ModelSerializer):
    """
    Serializer for the Book model.
    Handles read operations with nested author and category details.
    Handles write operations (create/update) using PrimaryKeyRelatedField for M2M relationships.
    """
    authors = AuthorSerializer(many=True, read_only=True)
    categories = CategorySerializer(many=True, read_only=True)
    is_favorite = serializers.SerializerMethodField()

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
            'description', 'cover_image', 
            'categories', 'category_ids',
            'total_borrows', 'date_added_to_system', 'last_updated',
            'available_copies_count', 'is_favorite'
        ]
    
    def get_is_favorite(self, obj):
        user = self.context['request'].user
        if user and user.is_authenticated:
            if not hasattr(user, 'favorite_books') or not isinstance(user.favorite_books, list):
                return False
            return any(fav_item.get('isbn') == obj.isbn for fav_item in user.favorite_books)
        return False

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

    book_isbn_for_request = serializers.CharField(
        write_only=True,
        required=False,
        help_text="ISBN of the book to request if no specific copy is chosen."
    )
    borrower_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.objects.all(),
        source='borrower',
        write_only=True,
        required=False
    )
    book_copy_id = serializers.PrimaryKeyRelatedField(
        queryset=BookCopy.objects.all(),
        source='book_copy',
        write_only=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = Borrowing
        fields = (
            'id', 'borrower', 'book_copy', 'issue_date', 'due_date', 'return_date',
            'status', 'fine_amount', 'notes_by_librarian',
            'book_isbn_for_request', 'book_copy_id', 'borrower_id'
        )
        read_only_fields = ('id', 'issue_date', 'return_date', 'fine_amount', 'notes_by_librarian')

    def validate(self, data):
        user = self.context['request'].user
        book_isbn = data.get('book_isbn_for_request')
        book_copy_instance = data.get('book_copy') # This will be a BookCopy model instance if book_copy_id was valid

        if not book_isbn and not book_copy_instance:
            raise serializers.ValidationError("Either 'book_isbn_for_request' (for automatic copy selection) or 'book_copy_id' (for a specific copy) must be provided.")

        if book_copy_instance: # If a specific copy is chosen
            if book_isbn and book_copy_instance.book.isbn != book_isbn:
                raise serializers.ValidationError("The chosen book copy does not belong to the specified ISBN.")
            if book_copy_instance.status != 'Available':
                # Allow staff to proceed if they are manually overriding or handling a special case
                # For user requests, it must be available.
                if not user.is_staff: #
                    raise serializers.ValidationError(f"The selected book copy '{book_copy_instance.copy_id}' is not available.")
        elif not book_isbn: # book_copy_instance is None, and book_isbn is also None
             raise serializers.ValidationError("Book ISBN must be provided for automatic copy selection.")

        due_date = data.get('due_date')
        if not due_date:
            raise serializers.ValidationError({"due_date": "Due date is required."})
        if due_date < timezone.now().date():
            raise serializers.ValidationError({"due_date": "Due date cannot be in the past."})

        return data

    def create(self, validated_data):
        user = self.context['request'].user

        # Determine the borrower
        # If 'borrower' (from borrower_id) is in validated_data, it means staff set it. Otherwise, use request.user.
        borrower_for_loan = validated_data.get('borrower', user)
        if validated_data.get('borrower') and validated_data.get('borrower') != user and not user.is_staff:
            raise serializers.ValidationError("You do not have permission to create a loan for another user.")
        validated_data['borrower'] = borrower_for_loan

        book_copy_instance = validated_data.get('book_copy') # This is already a BookCopy model instance
        book_isbn = validated_data.pop('book_isbn_for_request', None)

        if not book_copy_instance and book_isbn: # If no specific copy chosen, find one by ISBN
            book_obj = get_object_or_404(Book, isbn=book_isbn)

            # Prevent duplicate active/pending request for the same BOOK TITLE by the same user
            if Borrowing.objects.filter(
                borrower=borrower_for_loan,
                book_copy__book=book_obj,
                status__in=['REQUESTED', 'ACTIVE', 'OVERDUE']
            ).exists():
                raise serializers.ValidationError(f"You already have an active loan or pending request for '{book_obj.title}'.")

            available_copy = BookCopy.objects.filter(book=book_obj, status='Available').order_by('date_acquired', 'id').first()
            if not available_copy:
                raise serializers.ValidationError(f"No copies of '{book_obj.title}' are currently available to request.")
            validated_data['book_copy'] = available_copy
        elif not book_copy_instance: # Should have been caught by validate, but as a safeguard
            raise serializers.ValidationError("A book copy is required.")
        
        if not user.is_staff:
            validated_data['status'] = 'REQUESTED'
            validated_data.pop('issue_date', None) # Users cannot set issue_date for a request
        else: # Staff user
            current_status = validated_data.get('status')
            if not current_status:
                validated_data['status'] = 'ACTIVE' 

            if validated_data['status'] == 'ACTIVE' and 'issue_date' not in validated_data:
                validated_data['issue_date'] = timezone.now()

        borrowing_instance = Borrowing.objects.create(**validated_data)

        if borrowing_instance.status == 'ACTIVE':
            active_copy = borrowing_instance.book_copy
            if active_copy.status == 'Available':
                active_copy.status = 'On Loan'
                active_copy.save(update_fields=['status'])

        # TODO: Send notifications (e.g., using signals.py)

        return borrowing_instance


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