from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated, BasePermission
from django_filters.rest_framework import DjangoFilterBackend

from api.views import AuditLogMixin, CustomPagination
from inventory.models import AuditLog
from .models import Sale, Payment, CreditNote
from .serializers import SaleSerializer, PaymentSerializer, CreditNoteSerializer
from .services import delete_sale


class SalesAccess(BasePermission):
    """Any authenticated user can read and create sales; only admins delete."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method == "DELETE":
            return getattr(request.user, "role", None) == "admin"
        return True


class SaleViewSet(AuditLogMixin, ModelViewSet):
    """Sales: list (paginated, ?customer=<id> filter), detail, create, delete."""
    queryset = Sale.objects.select_related("customer", "user").prefetch_related(
        "items__product", "payments", "credit_notes__items"
    ).all()
    serializer_class = SaleSerializer
    permission_classes = [SalesAccess]
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["customer"]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def perform_destroy(self, instance):
        self._log(AuditLog.DELETE, instance)
        delete_sale(instance)


class PaymentViewSet(AuditLogMixin, ModelViewSet):
    """Record payments against a sale. History is read through the sale."""
    queryset = Payment.objects.select_related("sale", "sale__customer").all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "head", "options"]

    def perform_create(self, serializer):
        super().perform_create(serializer)


class CreditNoteViewSet(AuditLogMixin, ModelViewSet):
    """Record returns against a sale. History is read through the sale."""
    queryset = CreditNote.objects.select_related("sale__customer").prefetch_related("items").all()
    serializer_class = CreditNoteSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "head", "options"]
