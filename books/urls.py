from rest_framework.routers import DefaultRouter
from .views import BookViewSet, AuthorViewSet

router = DefaultRouter()
router.register('books', BookViewSet)
router.register('authors', AuthorViewSet)

urlpatterns = router.urls
