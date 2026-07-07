from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter

from users.models import CustomUser
from users.permissions import (
    IsAdminOrReadOnly, ManagerWriteOrReadOnly, SalesWriteOrReadOnly,
)
from inventory.models import Product, AuditLog
from customers.models import Customer, CustomerTag
from .serializers import (
    ProductSerializer, CustomUserSerializer, PromoteUserSerializer,
    CustomerSerializer, CustomerTagSerializer, AuditLogSerializer,
)


class AuditLogMixin:
    """Write an AuditLog row whenever a viewset creates, updates or deletes."""

    def _log(self, action, instance):
        try:
            AuditLog.objects.create(
                user=self.request.user if self.request.user.is_authenticated else None,
                action=action,
                model_name=instance.__class__.__name__,
                object_id=str(getattr(instance, "pk", "")),
                object_repr=str(instance)[:255],
            )
        except Exception:
            pass

    def perform_create(self, serializer):
        instance = serializer.save()
        self._log(AuditLog.CREATE, instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self._log(AuditLog.UPDATE, instance)

    def perform_destroy(self, instance):
        self._log(AuditLog.DELETE, instance)
        instance.delete()


class BulkDeleteMixin:
    @action(detail=False, methods=["post"], url_path="bulk-delete", permission_classes=[IsAdminOrReadOnly])
    def bulk_delete(self, request):
        ids = request.data.get("ids", [])
        if not ids:
            return Response({"detail": "No IDs provided."}, status=status.HTTP_400_BAD_REQUEST)
        self.queryset.model.objects.filter(id__in=ids).delete()
        return Response({"detail": "Deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })


class ProductViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [ManagerWriteOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "price", "stock"]
    ordering = ["name"]


class CustomerViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = Customer.objects.prefetch_related("tags").all()
    serializer_class = CustomerSerializer
    permission_classes = [SalesWriteOrReadOnly]
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["customer_type", "city", "is_active", "tags"]
    search_fields = ["name", "phone_number", "email", "city"]
    ordering_fields = ["name", "outstanding_balance", "credit_limit", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        qs = Customer.objects.prefetch_related("tags").all()
        has_balance = self.request.query_params.get("has_balance")
        if has_balance in ("true", "1"):
            qs = qs.filter(outstanding_balance__gt=0)
        return qs


class CustomerTagViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = CustomerTag.objects.all()
    serializer_class = CustomerTagSerializer
    permission_classes = [SalesWriteOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ["name"]


class UserViewSet(ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = CustomUserSerializer
    permission_classes = [IsAdminOrReadOnly]

    @action(detail=True, methods=["post"], permission_classes=[IsAdminOrReadOnly])
    def set_role(self, request, pk=None):
        user = self.get_object()
        ser = PromoteUserSerializer(user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response({"detail": "Role updated", "user": CustomUserSerializer(user).data})


class AuditLogViewSet(ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('user').all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['action', 'model_name', 'user']
    search_fields = ['object_repr', 'object_id']


class NotificationsView(APIView):
    """Overdue-invoice alerts for the notification bell: unpaid balances
    older than `overdue_days` (default 14)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from datetime import timedelta
        from django.utils.timezone import localdate
        from sales.models import Sale

        today = localdate()
        overdue_days = int(request.query_params.get("overdue_days", 14))
        cutoff = today - timedelta(days=overdue_days)

        items = []
        for sale in Sale.objects.select_related("customer").filter(date__lte=cutoff):
            if sale.balance > 0:
                items.append({
                    "type": "overdue_invoice",
                    "message": f"{sale.invoice_number} — {sale.customer.name} owes ₦{sale.balance:,.2f} ({(today - sale.date).days} days).",
                    "link": f"/sales/{sale.id}",
                })
        return Response({"count": len(items), "items": items})
