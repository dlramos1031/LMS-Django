from django.contrib import admin
from django.utils.html import format_html
from .models import Book, Author, Genre

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']

@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ['title', 'get_authors', 'get_genres', 'quantity']
    search_fields = ['title', 'summary']
    list_filter = ['genres', 'authors']
    filter_horizontal = ['authors', 'genres']  # adds dual list selector

    def get_authors(self, obj):
        return ", ".join([a.name for a in obj.authors.all()])
    get_authors.short_description = 'Authors'

    def get_genres(self, obj):
        return ", ".join([g.name for g in obj.genres.all()])
    get_genres.short_description = 'Genres'

    readonly_fields = ['cover_preview']

    def cover_preview(self, obj):
        if obj.cover_image:
            return format_html('<img src="{}" width="100" />', obj.cover_image.url)
        return "No cover"
