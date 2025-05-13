from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from users.views import staff_login_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('dashboard/login/', staff_login_view, name='staff_login'),

    # API routes
    path('api/', include('books.api_urls')), 
    path('api/auth/', include('users.api_urls')), 
    path('api/auth/password_reset/', include('django_rest_passwordreset.urls', namespace='password_reset')), 

    # Web routes
    path('', include('books.urls')), 
    path('', include('users.urls')), 
]

# Serve media files when in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
