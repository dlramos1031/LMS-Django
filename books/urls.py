from django.urls import path
from . import views

app_name = 'books'

urlpatterns = [
    # === Borrower Web Portal URLs ===
    path('portal/catalog/', views.BookPortalListView.as_view(), name='portal_book_list'),
    path('portal/book/<slug:isbn>/', views.BookPortalDetailView.as_view(), name='portal_book_detail'),
    
    path('portal/category/<int:category_id>/', views.books_by_category_portal_view, name='portal_books_by_category_id'),
    path('portal/category/<slug:category_slug>/', views.books_by_category_portal_view, name='portal_books_by_category_slug'),

    # === Staff Dashboard URLs ===
    path('dashboard/', views.staff_dashboard_home, name='staff_dashboard_home'),
]
