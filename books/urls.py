from django.urls import path
from . import views

app_name = 'books'

urlpatterns = [
    # Borrower Web Portal
    path('', views.BookPortalCatalogView.as_view(), name='portal_catalog'),
    path('book/<slug:isbn>/', views.BookPortalDetailView.as_view(), name='portal_book_detail'),
    path('borrow-request/submit/', views.portal_create_borrow_request_view, name='portal_borrow_request'),
    path('borrowing/<int:borrowing_id>/renew/', views.renew_book_view, name='portal_borrow_renew'),
    path('author/<int:pk>/', views.PortalAuthorDetailView.as_view(), name='portal_author_detail'),
    path('category/<int:pk>/', views.PortalCategoryDetailView.as_view(), name='portal_category_detail'),

    # Staff Dashboard
    path('dashboard/', views.staff_dashboard_home_view, name='dashboard_home'),

    # Book & Collection Management (Staff)
    path('dashboard/books/', views.StaffBookListView.as_view(), name='dashboard_book_list'),
    path('dashboard/books/add/', views.StaffBookCreateView.as_view(), name='dashboard_book_add'),
    path('dashboard/books/view/<slug:isbn>/', views.StaffBookDetailView.as_view(), name='dashboard_book_detail'),
    path('dashboard/books/edit/<slug:isbn>/', views.StaffBookUpdateView.as_view(), name='dashboard_book_edit'),
    path('dashboard/books/delete/<slug:isbn>/confirm/', views.StaffBookDeleteView.as_view(), name='dashboard_book_delete_confirm'),

    path('dashboard/book-copies/<slug:isbn>/', views.StaffBookCopiesManageView.as_view(), name='dashboard_bookcopy_list'),
    path('dashboard/book-copies/add/<slug:book_isbn>/', views.StaffBookCopyCreateView.as_view(), name='dashboard_bookcopy_add'),
    path('dashboard/book-copies/edit/<int:pk>/', views.StaffBookCopyUpdateView.as_view(), name='dashboard_bookcopy_edit'),
    path('dashboard/book-copies/delete/<int:pk>/confirm/', views.StaffBookCopyDeleteView.as_view(), name='dashboard_bookcopy_delete_confirm'),

    path('dashboard/categories/', views.StaffCategoryListView.as_view(), name='dashboard_category_list'),
    path('dashboard/categories/add/', views.StaffCategoryCreateView.as_view(), name='dashboard_category_add'),
    path('dashboard/categories/view/<int:pk>/', views.StaffCategoryDetailView.as_view(), name='dashboard_category_detail'),
    path('dashboard/categories/edit/<int:pk>/', views.StaffCategoryUpdateView.as_view(), name='dashboard_category_edit'),
    path('dashboard/categories/delete/<int:pk>/confirm/', views.StaffCategoryDeleteView.as_view(), name='dashboard_category_delete_confirm'),

    path('dashboard/authors/', views.StaffAuthorListView.as_view(), name='dashboard_author_list'),
    path('dashboard/authors/add/', views.StaffAuthorCreateView.as_view(), name='dashboard_author_add'),
    path('dashboard/authors/view/<int:pk>/', views.StaffAuthorDetailView.as_view(), name='dashboard_author_detail'),
    path('dashboard/authors/edit/<int:pk>/', views.StaffAuthorUpdateView.as_view(), name='dashboard_author_edit'),
    path('dashboard/authors/delete/<int:pk>/confirm/', views.StaffAuthorDeleteView.as_view(), name='dashboard_author_delete_confirm'),

    # Circulation Management (Staff)
    path('dashboard/circulation/issue/', views.staff_issue_book_view, name='dashboard_circulation_issue'),
    path('dashboard/circulation/return/', views.staff_return_book_view, name='dashboard_circulation_return'),
    path('dashboard/circulation/pending/', views.StaffPendingRequestsView.as_view(), name='dashboard_pending_requests'),
    path('dashboard/circulation/pending/approve/<int:borrowing_id>/', views.staff_approve_request_view, name='dashboard_approve_request'),
    path('dashboard/circulation/pending/reject/<int:borrowing_id>/', views.staff_reject_request_view, name='dashboard_reject_request'),
    path('dashboard/circulation/active-loans/', views.StaffActiveLoansView.as_view(), name='dashboard_active_loans'),
    path('dashboard/circulation/active-loans/<int:borrowing_id>/mark-returned/', views.staff_mark_loan_returned_view, name='dashboard_mark_loan_returned'),
    path('dashboard/circulation/history/', views.StaffBorrowingHistoryView.as_view(), name='dashboard_borrowing_history'),
    path('dashboard/circulation/reservations/', views.StaffReservationListView.as_view(), name='dashboard_reservations'),
]