from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BrandViewSet, CategoryViewSet, SizeViewSet, WareViewSet, WareVariantViewSet,
    BatchViewSet, ImageViewSet,UserViewSet
)

router = DefaultRouter()
router.register(r'brands', BrandViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'sizes', SizeViewSet)
router.register(r'wares', WareViewSet)
router.register(r'variants', WareVariantViewSet)
router.register(r'batches', BatchViewSet)
router.register(r'images', ImageViewSet)
router.register(r'users', UserViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
