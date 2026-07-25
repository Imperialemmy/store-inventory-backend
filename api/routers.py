from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProductViewSet, CustomerViewSet, NotificationsView,
    HealthView, RealtimeTicketView, OperationsSummaryView, InventoryMovementViewSet,
)
from sales.views import SaleViewSet, PaymentViewSet, RefundViewSet, CreditNoteViewSet
from users.views import UserAdminViewSet, AccountStatusView, LogoutView

router = DefaultRouter()
router.register(r'products', ProductViewSet)
router.register(r'customers', CustomerViewSet)
router.register(r'sales', SaleViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'refunds', RefundViewSet)
router.register(r'credit-notes', CreditNoteViewSet)
router.register(r'users', UserAdminViewSet)
router.register(r'inventory-movements', InventoryMovementViewSet)

urlpatterns = [
    path('health/', HealthView.as_view(), name='health'),
    path('realtime-ticket/', RealtimeTicketView.as_view(), name='realtime-ticket'),
    path('operations-summary/', OperationsSummaryView.as_view(), name='operations-summary'),
    path('notifications/', NotificationsView.as_view(), name='notifications'),
    path('auth/account-status/', AccountStatusView.as_view(), name='account-status'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('', include(router.urls)),
]
