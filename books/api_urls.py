from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BookViewSet, AuthorViewSet, GenreViewSet, BorrowingViewSet

router = DefaultRouter()
router.register('books', BookViewSet)
router.register('authors', AuthorViewSet)
router.register('genres', GenreViewSet)
router.register('borrow', BorrowingViewSet, basename='borrow')

urlpatterns = [
    path('', include(router.urls)),
]
