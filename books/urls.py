from rest_framework.routers import DefaultRouter
from .views import (BookViewSet, 
                    AuthorViewSet, 
                    GenreViewSet, 
                    BorrowingViewSet
                    )
from .views import (books_list_view,
                    book_detail_view, 
                    borrow_book_view,
                    librarian_dashboard_view,
                    approve_borrow_view,
                    reject_borrow_view,
                    mark_returned_view
                    )
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
    path('books/<int:pk>/borrow/', borrow_book_view, name='borrow_book'),

    path('dashboard/', librarian_dashboard_view, name='librarian_dashboard'),
    path('dashboard/approve/<int:borrow_id>/', approve_borrow_view, name='approve_borrow'),
    path('dashboard/reject/<int:borrow_id>/', reject_borrow_view, name='reject_borrow'),
    path('dashboard/return/<int:borrow_id>/', mark_returned_view, name='mark_returned'),
]
