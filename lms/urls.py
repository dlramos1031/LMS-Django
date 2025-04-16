from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # API routes
    path('api/auth/', include('users.api_urls')), 
    path('api/', include('books.api_urls')), 

    # Web routes
    path('', include('books.urls')), 
    path('', include('users.urls')), 
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
