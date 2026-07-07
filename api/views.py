from django.db.models import OuterRef, Subquery
from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from users.models import CustomUser
from .serializers import (
    BrandSerializer, CategorySerializer, SizeSerializer, WareSerializer,
    WareVariantSerializer, BatchSerializer, ImageSerializer, CustomUserSerializer,
    PromoteUserSerializer, SupplierSerializer, WarehouseSerializer, AuditLogSerializer,
    CustomerSerializer, CustomerTagSerializer,
)
from inventory.models import (
    Brand, Category, Size, Ware, WareVariant, Batch, Image,
    Supplier, Warehouse, AuditLog,
)
from customers.models import Customer, CustomerTag
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from inventory.filters import WareFilter
from inventory.services import low_stock_variants
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from users.permissions import (
    IsAdminOrReadOnly, ManagerWriteOrReadOnly,
    WarehouseWriteOrReadOnly, SalesWriteOrReadOnly,
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
            # Auditing must never break the underlying write.
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
    @action(detail=False, methods=["post"], url_path="bulk-delete", permission_classes=[IsAdminOrReadOnly],)
    def bulk_delete(self, request):
        ids = request.data.get("ids", [])
        if not ids:
            return Response({"detail": "No IDs provided."}, status=status.HTTP_400_BAD_REQUEST)

        self.queryset.model.objects.filter(id__in=ids).delete()
        return Response({"detail": "Deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class CustomPagination(PageNumberPagination):
    page_size = 10  # Set to 10 items per page
    page_size_query_param = 'page_size'  # Optional: Allow overriding via ?page_size=X
    max_page_size = 100  # Optional: Cap for safety

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })


class BrandViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = Brand.objects.all()
    permission_classes = [ManagerWriteOrReadOnly]
    serializer_class = BrandSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name']

class CategoryViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = Category.objects.all()
    permission_classes = [ManagerWriteOrReadOnly]
    serializer_class = CategorySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name']

class SizeViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    permission_classes = [ManagerWriteOrReadOnly]
    queryset = Size.objects.all()
    serializer_class = SizeSerializer


class WareViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = Ware.objects.all()
    serializer_class = WareSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = WareFilter
    search_fields = ['name']
    permission_classes = [ManagerWriteOrReadOnly]


class SupplierViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [ManagerWriteOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name', 'contact_name', 'email']


class WarehouseViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [ManagerWriteOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name']


class WareVariantViewSet(AuditLogMixin, ModelViewSet):
    queryset = WareVariant.objects.all()
    serializer_class = WareVariantSerializer
    pagination_class = CustomPagination
    permission_classes = [ManagerWriteOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['ware__name']  # Search by ware name
    ordering_fields = ['last_updated']  # Order by last updated
    ordering = ['-last_updated']  # Default: last updated first

    def get_queryset(self):
        queryset = WareVariant.objects.all()
        # Annotate with the latest batch updated_at
        latest_batch = Batch.objects.filter(variant=OuterRef('pk')).order_by('-updated_at').values('updated_at')[:1]
        return queryset.annotate(last_updated=Subquery(latest_batch))

    @action(detail=False, methods=["get"], url_path="low-stock")
    def low_stock(self, request):
        """List variants at or below their reorder point.

        Optional ``?warehouse=<id>`` scopes stock to a single location.
        """
        warehouse = request.query_params.get("warehouse")
        variants = low_stock_variants(warehouse=warehouse or None)
        page = self.paginate_queryset(variants)
        target = page if page is not None else variants
        serializer = self.get_serializer(target, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

class BatchViewSet(AuditLogMixin, ModelViewSet):
    permission_classes = [WarehouseWriteOrReadOnly]
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['variant', 'warehouse', 'supplier']

class ImageViewSet(AuditLogMixin, ModelViewSet):
    permission_classes = [ManagerWriteOrReadOnly]
    queryset = Image.objects.all()
    serializer_class = ImageSerializer


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
        # ?has_balance=true narrows to customers who currently owe money.
        has_balance = self.request.query_params.get("has_balance")
        if has_balance in ("true", "1"):
            qs = qs.filter(outstanding_balance__gt=0)
        return qs

    @action(detail=False, methods=["get"], url_path="debt-aging")
    def debt_aging(self, request):
        """Unpaid balances per customer, bucketed by invoice age in days
        (0–30, 31–60, 61–90, 90+)."""
        from decimal import Decimal
        from django.utils.timezone import localdate
        from sales.models import Sale

        today = localdate()
        rows = {}
        for sale in Sale.objects.select_related("customer").filter(customer__isnull=False):
            balance = sale.balance
            if balance <= 0:
                continue
            age = (today - sale.date).days
            bucket = "0_30" if age <= 30 else "31_60" if age <= 60 else "61_90" if age <= 90 else "over_90"
            row = rows.setdefault(sale.customer_id, {
                "customer": sale.customer_id,
                "customer_name": sale.customer.name,
                "0_30": Decimal("0"), "31_60": Decimal("0"),
                "61_90": Decimal("0"), "over_90": Decimal("0"),
                "total": Decimal("0"),
            })
            row[bucket] += balance
            row["total"] += balance

        results = sorted(rows.values(), key=lambda r: r["total"], reverse=True)
        for row in results:
            for key in ("0_30", "31_60", "61_90", "over_90", "total"):
                row[key] = str(row[key].quantize(Decimal("0.01")))
        return Response({"as_of": today, "results": results})


class CustomerTagViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = CustomerTag.objects.all()
    serializer_class = CustomerTagSerializer
    permission_classes = [ManagerWriteOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ["name"]


class NotificationsView(APIView):
    """Aggregated operational alerts for the notification bell.

    - Low stock: variants at/below their reorder point.
    - Overdue invoices: unpaid balances older than `overdue_days` (default 14).
    - Expiring batches: stock that expires within `expiry_days` (default 30).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from datetime import timedelta
        from django.utils.timezone import localdate
        from inventory.services import low_stock_variants
        from sales.models import Sale

        today = localdate()
        overdue_days = int(request.query_params.get("overdue_days", 14))
        expiry_days = int(request.query_params.get("expiry_days", 30))

        items = []

        for variant in low_stock_variants():
            items.append({
                "type": "low_stock",
                "message": f"{variant.ware.name} ({variant.size}) is low: {variant.get_stock()} left (reorder at {variant.reorder_point}).",
                "link": f"/wares/{variant.ware_id}",
            })

        cutoff = today - timedelta(days=overdue_days)
        for sale in Sale.objects.select_related("customer").filter(date__lte=cutoff):
            if sale.balance > 0:
                items.append({
                    "type": "overdue_invoice",
                    "message": f"{sale.invoice_number} — {sale.customer.name} owes ₦{sale.balance:,.2f} ({(today - sale.date).days} days).",
                    "link": f"/sales/{sale.id}",
                })

        expiring = Batch.objects.select_related("variant__ware").filter(
            is_expired=False, quantity__gt=0,
            expiry_date__gte=today, expiry_date__lte=today + timedelta(days=expiry_days),
        )
        for batch in expiring:
            items.append({
                "type": "expiring_batch",
                "message": f"Batch {batch.lot_number or batch.id} of {batch.variant.ware.name} expires {batch.expiry_date} ({batch.quantity} units).",
                "link": f"/wares/{batch.variant.ware_id}",
            })

        return Response({"count": len(items), "items": items})


class AuditLogViewSet(ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('user').all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['action', 'model_name', 'user']
    search_fields = ['object_repr', 'object_id']

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