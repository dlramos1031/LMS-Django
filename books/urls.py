from rest_framework.routers import DefaultRouter
from .views import BookViewSet, AuthorViewSet, GenreViewSet, BorrowingViewSet
from .views import books_list_view, book_detail_view
from django.urls import path, include

router = DefaultRouter()
router.register('books', BookViewSet)
router.register('authors', AuthorViewSet)
router.register('genres', GenreViewSet)
router.register('borrow', BorrowingViewSet, basename='borrow')

urlpatterns = [
    path('api/', include(router.urls)),
    path('books/', books_list_view, name='books_list'),
    path('books/<int:pk>/', book_detail_view, name='book_detail'),
]
