from rest_framework import serializers
from .models import Author, Book

class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = '__all__'

class BookSerializer(serializers.ModelSerializer):
    authors = AuthorSerializer(many=True, read_only=True)
    author_ids = serializers.PrimaryKeyRelatedField(
        queryset=Author.objects.all(), many=True, write_only=True, source='authors'
    )

    class Meta:
        model = Book
        fields = ['id', 'title', 'summary', 'cover_image', 'open_library_id',
                  'quantity', 'is_available', 'authors', 'author_ids']
        read_only_fields = ['is_available']
