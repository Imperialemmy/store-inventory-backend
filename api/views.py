from rest_framework.viewsets import ModelViewSet
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum
from django.utils.timezone import now
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import OrderingFilter, SearchFilter
from django_filters import rest_framework as filters

from users.permissions import AdminWriteOrReadOnly, CustomerAccess
from inventory.models import Product, AuditLog, InventoryMovement, StockReservation
from inventory.services import adjust_inventory
from inventory.quantities import parse_quarter_quantity, parse_stored_quantity
from customers.models import Customer
from .serializers import (
    ProductSerializer, CustomerSerializer, InventoryMovementSerializer,
)
from .realtime_auth import create_websocket_ticket
import logging

logger = logging.getLogger(__name__)


class AuditLogMixin:
    """Write an AuditLog row whenever a viewset creates, updates or deletes.

    The trail is internal (readable in the Django admin); there is no API
    endpoint for it.
    """

    def _snapshot(self, instance):
        result = {}
        for field in instance._meta.concrete_fields:
            value = getattr(instance, field.attname, None)
            result[field.name] = str(value) if value is not None else None
        return result

    def _log(self, action, instance, changes=None):
        try:
            AuditLog.objects.create(
                user=self.request.user if self.request.user.is_authenticated else None,
                action=action,
                model_name=instance.__class__.__name__,
                object_id=str(getattr(instance, "pk", "")),
                object_repr=str(instance)[:255],
                changes=changes,
            )
        except Exception:
            logger.exception("Audit log write failed for %s %s", action, instance)

    def perform_create(self, serializer):
        instance = serializer.save()
        self._log(AuditLog.CREATE, instance, {"after": self._snapshot(instance)})

    def perform_update(self, serializer):
        before = self._snapshot(serializer.instance)
        instance = serializer.save()
        self._log(AuditLog.UPDATE, instance, {
            "before": before,
            "after": self._snapshot(instance),
        })

    def perform_destroy(self, instance):
        self._log(AuditLog.DELETE, instance, {"before": self._snapshot(instance)})
        instance.delete()


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        from django.conf import settings
        return Response({
            "status": "ok",
            "default_vat_rate": str(settings.DEFAULT_VAT_RATE),
        })


class RealtimeTicketView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({"ticket": create_websocket_ticket(request.user)})


class StockReservationView(APIView):
    """Atomically replace the current device's connected-cart reservations."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        device_id = str(request.data.get("device_id") or "").strip()
        raw_items = request.data.get("items", [])
        if not device_id or len(device_id) > 100:
            return Response({"detail": "A valid device ID is required."}, status=400)
        if not isinstance(raw_items, list):
            return Response({"detail": "Items must be a list."}, status=400)

        requested = {}
        try:
            for row in raw_items:
                product_id = int(row["product"])
                quantity = parse_quarter_quantity(row["quantity"])
                if product_id in requested:
                    raise ValueError
                requested[product_id] = quantity
        except (TypeError, ValueError, KeyError):
            return Response({
                "detail": "Each product needs a positive quantity in quarter-unit steps."
            }, status=400)

        current_time = now()
        expires_at = current_time + timedelta(seconds=settings.STOCK_RESERVATION_SECONDS)
        with transaction.atomic():
            StockReservation.objects.filter(expires_at__lte=current_time).delete()
            products = {
                product.pk: product
                for product in Product.objects.select_for_update().filter(pk__in=sorted(requested))
            }
            if len(products) != len(requested):
                return Response({"detail": "One or more products are no longer available."}, status=400)

            own = StockReservation.objects.select_for_update().filter(
                user=request.user, device_id=device_id
            )
            conflicts = []
            availability = []
            for product_id, quantity in requested.items():
                product = products[product_id]
                reserved_elsewhere = StockReservation.objects.filter(
                    product_id=product_id, expires_at__gt=current_time
                ).exclude(user=request.user, device_id=device_id).aggregate(
                    total=Sum("quantity")
                )["total"] or Decimal("0")
                available = max(product.stock - reserved_elsewhere, Decimal("0"))
                if quantity > available:
                    conflicts.append({
                        "product": product_id,
                        "product_name": product.name,
                        "requested": quantity,
                        "available": available,
                    })
                availability.append({
                    "product": product_id,
                    "stock": product.stock,
                    "available": available,
                })

            if conflicts:
                return Response({
                    "detail": "Some items are no longer available in the requested quantity.",
                    "conflicts": conflicts,
                }, status=409)

            own.exclude(product_id__in=requested).delete()
            for product_id, quantity in requested.items():
                StockReservation.objects.update_or_create(
                    user=request.user,
                    device_id=device_id,
                    product_id=product_id,
                    defaults={"quantity": quantity, "expires_at": expires_at},
                )

        return Response({
            "reserved": availability,
            "expires_at": expires_at,
            "offline_stock_safety_threshold": settings.OFFLINE_STOCK_SAFETY_THRESHOLD,
        })


class OperationsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Sum
        from django.utils.timezone import localdate
        from sales.models import Sale, Payment

        today = localdate()
        sales = Sale.objects.filter(date=today)
        payments = Payment.objects.filter(date=today)
        payment_totals = {
            method: str(
                payments.filter(method=method).aggregate(total=Sum("amount"))["total"] or 0
            )
            for method in (Payment.CASH, Payment.TRANSFER, Payment.POS)
        }
        low_stock = Product.objects.filter(stock__lte=models.F("reorder_level")).count()
        attention = Sale.objects.filter(
            inventory_attention=True, inventory_resolution=""
        ).count()
        outstanding_sales = Sale.objects.prefetch_related(
            "payments", "refunds", "credit_notes__items"
        ).all()
        outstanding = sum(
            (sale.receivable for sale in outstanding_sales), Decimal("0")
        )
        refunds_due = sum(
            (sale.refund_due for sale in outstanding_sales), Decimal("0")
        )
        return Response({
            "date": today,
            "sales_total": str(sales.aggregate(total=Sum("total"))["total"] or 0),
            "sale_count": sales.count(),
            "payments": payment_totals,
            "low_stock_count": low_stock,
            "inventory_attention_count": attention,
            "outstanding_total": str(outstanding),
            "refunds_due_total": str(refunds_due),
        })


class CustomPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 1000

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'page': self.page.number,
            'page_size': self.get_page_size(self.request),
            'total_pages': self.page.paginator.num_pages,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })


class ProductFilter(filters.FilterSet):
    category = filters.CharFilter(field_name="category", lookup_expr="iexact")
    stock_status = filters.CharFilter(method="filter_stock_status")

    def filter_stock_status(self, queryset, _name, value):
        if value == "in_stock":
            return queryset.filter(stock__gt=models.F("reorder_level"))
        if value == "low_stock":
            return queryset.filter(
                stock__gt=0,
                stock__lte=models.F("reorder_level"),
            )
        if value == "out_of_stock":
            return queryset.filter(stock__lte=0)
        return queryset

    class Meta:
        model = Product
        fields = ["category", "stock_status"]


class ProductViewSet(AuditLogMixin, ModelViewSet):
    """Products: CRUD plus searchable, filterable, paginated directory reads."""
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [AdminWriteOrReadOnly]
    pagination_class = CustomPagination
    filter_backends = [filters.DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ["name"]
    ordering_fields = ["name", "stock", "updated_at"]
    ordering = ["name"]

    @action(detail=False, methods=["get"])
    def categories(self, request):
        categories = (
            self.get_queryset()
            .exclude(category="")
            .values_list("category", flat=True)
            .distinct()
            .order_by("category")
        )
        return Response(list(categories))

    @transaction.atomic
    def perform_create(self, serializer):
        try:
            requested_stock = parse_quarter_quantity(
                serializer.validated_data.get("stock", 0), allow_zero=True
            )
        except ValueError as exc:
            raise ValidationError({"stock": str(exc)}) from exc
        instance = serializer.save(stock=0)
        if requested_stock:
            adjust_inventory(
                product=instance,
                quantity=requested_stock,
                reason=InventoryMovement.OPENING,
                user=self.request.user,
                note="Opening stock",
            )
            instance.refresh_from_db()
        self._log(AuditLog.CREATE, instance, {"after": self._snapshot(instance)})

    @transaction.atomic
    def perform_update(self, serializer):
        before = self._snapshot(serializer.instance)
        old_stock = serializer.instance.stock
        try:
            requested_stock = parse_stored_quantity(
                serializer.validated_data.pop("stock", old_stock)
            )
            difference = requested_stock - old_stock
            if difference:
                parse_quarter_quantity(difference, allow_negative=True)
        except ValueError as exc:
            raise ValidationError({"stock": str(exc)}) from exc
        instance = serializer.save()
        if difference:
            adjust_inventory(
                product=instance,
                quantity=difference,
                reason=InventoryMovement.CORRECTION,
                user=self.request.user,
                note="Stock count changed from product editor",
            )
            instance.refresh_from_db()
        self._log(AuditLog.UPDATE, instance, {
            "before": before,
            "after": self._snapshot(instance),
        })


class InventoryMovementViewSet(ModelViewSet):
    queryset = InventoryMovement.objects.select_related("product", "sale", "user").all()
    serializer_class = InventoryMovementSerializer
    permission_classes = [AdminWriteOrReadOnly]
    http_method_names = ["get", "post", "head", "options"]

    def perform_create(self, serializer):
        movement = adjust_inventory(
            product=serializer.validated_data["product"],
            quantity=serializer.validated_data["quantity"],
            reason=serializer.validated_data["reason"],
            user=self.request.user,
            note=serializer.validated_data.get("note", ""),
            event_at=serializer.validated_data.get("event_at"),
        )
        serializer.instance = movement


class CustomerViewSet(AuditLogMixin, ModelViewSet):
    """Customers: full CRUD, paginated (?page_size=N)."""
    WALK_IN_NAME = "Walk-in Customer"

    queryset = Customer.objects.prefetch_related("tags").all()
    serializer_class = CustomerSerializer
    permission_classes = [CustomerAccess]
    pagination_class = CustomPagination
    filter_backends = [filters.DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["city", "is_active"]
    search_fields = ["name", "phone_number", "city"]
    ordering_fields = ["name", "created_at", "updated_at"]
    ordering = ["name"]

    @action(detail=False, methods=["get"], url_path="walk-in")
    def walk_in(self, request):
        """Return the shared 'Walk-in Customer', creating it once on first use.

        Lets the POS ring up a casual sale without capturing any details —
        every anonymous sale is grouped under this single record.
        """
        customer = Customer.objects.filter(name=self.WALK_IN_NAME).first()
        if customer is None:
            customer = Customer.objects.create(name=self.WALK_IN_NAME, user=request.user)
        return Response(self.get_serializer(customer).data)


class NotificationsView(APIView):
    """Operational alerts for stock and overdue customer balances."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from datetime import timedelta
        from django.utils.timezone import localdate
        from sales.models import Sale

        today = localdate()
        overdue_days = int(request.query_params.get("overdue_days", 14))
        cutoff = today - timedelta(days=overdue_days)

        items = []
        low_stock_products = Product.objects.filter(
            stock__lte=models.F("reorder_level")
        ).order_by("stock", "name")
        for product in low_stock_products:
            status_label = "out of stock" if product.stock <= 0 else f"low on stock ({product.stock} left)"
            stock_status = "out_of_stock" if product.stock <= 0 else "low_stock"
            items.append({
                "type": "low_stock",
                "message": f"{product.name} is {status_label}.",
                "link": f"/products?stock_status={stock_status}",
            })

        conflicts = Sale.objects.select_related("customer").filter(
            inventory_attention=True, inventory_resolution=""
        ).order_by("-synced_at")
        for sale in conflicts:
            items.append({
                "type": "stock_conflict",
                "message": f"{sale.invoice_number} has an unresolved stock conflict.",
                "link": f"/sales/{sale.id}",
            })

        sales = Sale.objects.select_related("customer").prefetch_related(
            "payments", "refunds", "credit_notes__items"
        ).filter(date__lte=cutoff)
        for sale in sales:
            if sale.receivable > 0:
                items.append({
                    "type": "overdue_invoice",
                    "message": f"{sale.invoice_number} — {sale.customer.name} owes ₦{sale.receivable:,.2f} ({(today - sale.date).days} days).",
                    "link": f"/sales/{sale.id}",
                })
        return Response({"count": len(items), "items": items})
