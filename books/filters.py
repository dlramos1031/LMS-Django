import django_filters
from .models import Book, Author, Category

class BookFilter(django_filters.FilterSet):
    """
    FilterSet for the Book model.
    Allows filtering books by various criteria including title, authors, and categories.
    """
    title = django_filters.CharFilter(
        field_name='title', 
        lookup_expr='icontains', 
        label='Title contains'
    )
    
    authors_name = django_filters.CharFilter(
        field_name='authors__name', 
        lookup_expr='icontains', 
        label='Author name contains'
    )
    
    categories_name = django_filters.CharFilter(
        field_name='categories__name', 
        lookup_expr='icontains', 
        label='Category name contains'
    )

    category = django_filters.ModelChoiceFilter(
        queryset=Category.objects.all(),
        field_name='categories',
        label='Category',
    )

    publisher = django_filters.CharFilter(
        field_name='publisher',
        lookup_expr='icontains',
        label='Publisher contains'
    )

    publication_year = django_filters.NumberFilter(
        field_name='publication_date__year',
        label='Publication Year'
    )
    
    isbn = django_filters.CharFilter(
        field_name='isbn',
        lookup_expr='exact',
        label='ISBN'
    )

    class Meta:
        model = Book
        fields = [
            'title', 
            'authors_name', 
            'categories_name', 
            'category', 
            'publisher',
            'publication_year',
            'isbn',
        ]

