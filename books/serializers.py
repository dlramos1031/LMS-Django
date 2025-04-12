from rest_framework import serializers
from .models import Author, Book, Genre

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

    class Meta:
        model = Book
        fields = [
            'id', 'title', 'summary', 'cover_image', 'open_library_id',
            'quantity', 'is_available', 'authors', 'author_ids',
            'genres', 'genre_ids'
        ]
        read_only_fields = ['is_available']
