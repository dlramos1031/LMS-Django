from django.urls import path
from . import views

app_name = 'books'

urlpatterns = [
    # === Borrower Web Portal URLs ===
    path('portal/catalog/', views.BookPortalListView.as_view(), name='portal_book_list'),
    path('portal/book/<slug:isbn>/', views.BookPortalDetailView.as_view(), name='portal_book_detail'),

    # === Staff Dashboard URLs ===
    path('dashboard/', views.staff_dashboard_home, name='staff_dashboard_home'),
]
