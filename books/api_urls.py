from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AuthorViewSet, BookViewSet, CategoryViewSet,
    BookCopyViewSet, BorrowingViewSet, NotificationViewSet
)

router = DefaultRouter()
router.register(r'authors', AuthorViewSet)
router.register(r'books', BookViewSet, basename='book')
router.register(r'categories', CategoryViewSet)
router.register(r'book-copies', BookCopyViewSet, basename='bookcopy')
router.register(r'borrowings', BorrowingViewSet, basename='borrowing')
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
]
