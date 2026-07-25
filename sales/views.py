from rest_framework.viewsets import ModelViewSet
from rest_framework import status
from rest_framework.response import Response
from django.db import IntegrityError
from decimal import Decimal, InvalidOperation
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.decorators import action
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters

from api.views import AuditLogMixin, CustomPagination
from inventory.models import AuditLog
from users.permissions import AdminOnly
from .models import Sale, Payment, Refund, CreditNote
from .serializers import (
    SaleSerializer, PaymentSerializer, RefundSerializer, CreditNoteSerializer,
)
from .services import delete_sale


class SalesAccess(BasePermission):
    """Any authenticated user can read and create sales; only admins delete."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method == "DELETE":
            return getattr(request.user, "role", None) == "admin"
        return True


class SaleFilter(filters.FilterSet):
    date_from = filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = Sale
        fields = ["customer", "date_from", "date_to"]


class SaleViewSet(AuditLogMixin, ModelViewSet):
    """Sales: list (paginated, ?customer=<id> filter), detail, create, delete."""
    queryset = Sale.objects.select_related("customer", "user").prefetch_related(
        "items__product", "payments", "refunds", "credit_notes__items"
    ).all()
    serializer_class = SaleSerializer
    permission_classes = [SalesAccess]
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = SaleFilter
    search_fields = ["invoice_number", "customer__name"]
    ordering_fields = ["date", "created_at", "invoice_number"]
    ordering = ["-date", "-id"]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def _same_idempotent_request(self, sale, data):
        try:
            if int(data.get("customer")) != sale.customer_id:
                return False
            requested = sorted(
                (
                    int(item["product"]),
                    int(item["quantity"]),
                    Decimal(str(item["unit_price"])) if item.get("unit_price") is not None else None,
                )
                for item in data.get("items", [])
            )
            existing_by_product = {
                item.product_id: item for item in sale.items.all()
            }
            if len(requested) != len(existing_by_product):
                return False
            return all(
                product_id in existing_by_product
                and quantity == existing_by_product[product_id].quantity
                and (price is None or price == existing_by_product[product_id].unit_price)
                for product_id, quantity, price in requested
            )
        except (TypeError, ValueError, KeyError, InvalidOperation):
            return False

    def create(self, request, *args, **kwargs):
        client_sale_id = request.data.get("client_sale_id")
        if client_sale_id:
            existing = self.get_queryset().filter(client_sale_id=client_sale_id).first()
            if existing:
                if not self._same_idempotent_request(existing, request.data):
                    return Response(
                        {"detail": "This sale reference was already used for different sale data."},
                        status=status.HTTP_409_CONFLICT,
                    )
                return Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
        try:
            return super().create(request, *args, **kwargs)
        except IntegrityError:
            # Two sync workers can race after both pass the first lookup. The
            # unique database constraint chooses one winner; return it to the
            # other worker only when the payload is the same.
            existing = self.get_queryset().filter(client_sale_id=client_sale_id).first()
            if existing and self._same_idempotent_request(existing, request.data):
                return Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
            raise

    def perform_destroy(self, instance):
        instance._acting_user = self.request.user
        self._log(AuditLog.DELETE, instance)
        delete_sale(instance)

    @action(detail=True, methods=["post"], permission_classes=[AdminOnly], url_path="resolve-stock-conflict")
    def resolve_stock_conflict(self, request, pk=None):
        sale = self.get_object()
        if not sale.inventory_attention:
            return Response({"detail": "This invoice has no stock conflict."}, status=400)
        if sale.inventory_resolution:
            return Response({
                "detail": "This stock conflict has already been reconciled."
            }, status=status.HTTP_409_CONFLICT)
        resolution = str(request.data.get("resolution") or "").strip()
        choices = {choice[0] for choice in sale.INVENTORY_RESOLUTION_CHOICES}
        if resolution not in choices:
            return Response({"detail": "Choose a valid stock-conflict resolution."}, status=400)
        note = str(request.data.get("note") or "").strip()
        if not note:
            return Response({"detail": "Add a short reconciliation note."}, status=400)
        if resolution == "stock_corrected":
            negative_products = sale.items.filter(product__stock__lt=0).values_list("product__name", flat=True)
            if negative_products:
                return Response({
                    "detail": f"Correct or restock these products first: {', '.join(negative_products)}."
                }, status=400)
        before = self._snapshot(sale)
        sale.inventory_resolution = resolution
        sale.inventory_resolution_note = note[:255]
        sale.inventory_resolved_by = request.user
        sale.inventory_resolved_at = now()
        sale.save(update_fields=[
            "inventory_resolution", "inventory_resolution_note",
            "inventory_resolved_by", "inventory_resolved_at", "updated_at",
        ])
        self._log(AuditLog.UPDATE, sale, {"before": before, "after": self._snapshot(sale)})
        return Response(self.get_serializer(sale).data)


class PaymentViewSet(AuditLogMixin, ModelViewSet):
    """Record payments against a sale. History is read through the sale."""
    queryset = Payment.objects.select_related("sale", "sale__customer").all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "head", "options"]

    def perform_create(self, serializer):
        super().perform_create(serializer)


class RefundViewSet(AuditLogMixin, ModelViewSet):
    """Record customer refund payouts. History is read through the sale."""
    queryset = Refund.objects.select_related("sale", "sale__customer", "user").all()
    serializer_class = RefundSerializer
    permission_classes = [AdminOnly]
    http_method_names = ["post", "head", "options"]


class CreditNoteViewSet(AuditLogMixin, ModelViewSet):
    """Record returns against a sale. History is read through the sale."""
    queryset = CreditNote.objects.select_related("sale__customer").prefetch_related("items").all()
    serializer_class = CreditNoteSerializer
    permission_classes = [AdminOnly]
    http_method_names = ["post", "head", "options"]
