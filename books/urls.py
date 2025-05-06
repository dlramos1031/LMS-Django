from django.urls import path
from .views import (
    books_list_view,
    book_detail_view,
    borrow_book_view,
    librarian_dashboard_view,
    approve_borrow_view,
    reject_borrow_view,
    mark_returned_view,
    add_book_view,
    edit_book_view,
    delete_book_view,
    dashboard_pending_view,
    dashboard_active_view,
    dashboard_history_view,
    dashboard_books_view,
)

urlpatterns = [
    # Book List & Detail
    path('books/', books_list_view, name='books_list'),
    path('books/<int:pk>/', book_detail_view, name='book_detail'),
    path('books/<int:pk>/borrow/', borrow_book_view, name='borrow_book'),

    # Librarian dashboard & Borrowing Management
    path('dashboard/', librarian_dashboard_view, name='librarian_dashboard'),
    path('dashboard/pending/', dashboard_pending_view, name='dashboard_pending'),
    path('dashboard/active/', dashboard_active_view, name='dashboard_active'),
    path('dashboard/history/', dashboard_history_view, name='dashboard_history'),
    path('dashboard/books/', dashboard_books_view, name='dashboard_books'),

    path('dashboard/approve/<int:borrow_id>/', approve_borrow_view, name='approve_borrow'),
    path('dashboard/reject/<int:borrow_id>/', reject_borrow_view, name='reject_borrow'),
    path('dashboard/return/<int:borrow_id>/', mark_returned_view, name='mark_returned'),

    # Dashboard Book Management
    path('dashboard/books/add/', add_book_view, name='add_book'),
    path('dashboard/books/<int:book_id>/edit/', edit_book_view, name='edit_book'),
    path('dashboard/books/<int:book_id>/delete/', delete_book_view, name='delete_book'),
]
