from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductViewSet, CustomerViewSet, CustomerTagViewSet,
    UserViewSet, AuditLogViewSet, NotificationsView,
)
from sales.views import SaleViewSet, PaymentViewSet, CreditNoteViewSet

router = DefaultRouter()
router.register(r'products', ProductViewSet)
router.register(r'customers', CustomerViewSet)
router.register(r'customer-tags', CustomerTagViewSet)
router.register(r'sales', SaleViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'credit-notes', CreditNoteViewSet)
router.register(r'users', UserViewSet)
router.register(r'audit-logs', AuditLogViewSet)

urlpatterns = [
    path('notifications/', NotificationsView.as_view(), name='notifications'),
    path('', include(router.urls)),
]
