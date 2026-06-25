from decimal import Decimal
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count, F, DecimalField
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter

from api.views import AuditLogMixin, CustomPagination
from inventory.models import AuditLog
from .models import Sale, SaleItem, Payment
from .serializers import SaleSerializer, PaymentSerializer
from .services import delete_sale, recalculate_customer_balance


def _money(value):
    """Serialize a Decimal/None money value to a fixed 2-dp string."""
    return str((value or Decimal("0")).quantize(Decimal("0.01")))


class SalesAccess(BasePermission):
    """Any authenticated user can read and create sales; only admins delete."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method == "DELETE":
            return getattr(request.user, "role", None) == "admin"
        return True


class SaleViewSet(AuditLogMixin, ModelViewSet):
    queryset = Sale.objects.select_related("customer", "user").prefetch_related(
        "items__variant__ware", "payments"
    ).all()
    serializer_class = SaleSerializer
    permission_classes = [SalesAccess]
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["customer", "customer__customer_type", "date"]
    search_fields = ["invoice_number", "customer__name"]
    ordering_fields = ["created_at", "date", "total"]
    ordering = ["-created_at"]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def perform_destroy(self, instance):
        # Return stock and refresh the customer balance before removing.
        self._log(AuditLog.DELETE, instance)
        delete_sale(instance)

    @action(detail=False, methods=["get"])
    def report(self, request):
        """Sales analytics over an optional date range.

        Query params: start, end (YYYY-MM-DD), period (day|week|month).
        Returns totals, a period breakdown, top products, and revenue
        split by customer type and salesperson.
        """
        sales = Sale.objects.all()
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        if start:
            sales = sales.filter(date__gte=start)
        if end:
            sales = sales.filter(date__lte=end)

        period = request.query_params.get("period", "day")
        trunc = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth}.get(period, TruncDay)

        revenue_expr = Sum(
            F("quantity") * F("unit_price"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )

        total_sales = sales.aggregate(s=Sum("total"))["s"] or Decimal("0")
        collected = Payment.objects.filter(sale__in=sales).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        invoice_count = sales.count()

        by_period = (
            sales.annotate(bucket=trunc("date"))
            .values("bucket")
            .annotate(total=Sum("total"), invoices=Count("id"))
            .order_by("bucket")
        )
        top_products = (
            SaleItem.objects.filter(sale__in=sales)
            .values("variant__ware__name", "variant__size__size", "variant__size__size_unit")
            .annotate(units=Sum("quantity"), revenue=revenue_expr)
            .order_by("-revenue")[:10]
        )
        by_type = (
            sales.values("customer__customer_type")
            .annotate(total=Sum("total"), invoices=Count("id"))
            .order_by("-total")
        )
        by_salesperson = (
            sales.values("user__username")
            .annotate(total=Sum("total"), invoices=Count("id"))
            .order_by("-total")
        )

        return Response({
            "range": {"start": start, "end": end, "period": period},
            "totals": {
                "sales": _money(total_sales),
                "collected": _money(collected),
                "outstanding": _money(total_sales - collected),
                "invoices": invoice_count,
            },
            "by_period": [
                {"bucket": row["bucket"], "total": _money(row["total"]), "invoices": row["invoices"]}
                for row in by_period
            ],
            "top_products": [
                {
                    "name": f'{row["variant__ware__name"]} ({row["variant__size__size"]}{row["variant__size__size_unit"] or ""})',
                    "quantity": row["units"],
                    "revenue": _money(row["revenue"]),
                }
                for row in top_products
            ],
            "by_customer_type": [
                {"customer_type": row["customer__customer_type"], "total": _money(row["total"]), "invoices": row["invoices"]}
                for row in by_type
            ],
            "by_salesperson": [
                {"salesperson": row["user__username"] or "—", "total": _money(row["total"]), "invoices": row["invoices"]}
                for row in by_salesperson
            ],
        })


class PaymentViewSet(AuditLogMixin, ModelViewSet):
    queryset = Payment.objects.select_related("sale", "sale__customer").all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["sale", "method"]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def perform_create(self, serializer):
        super().perform_create(serializer)  # saves + writes audit log
        recalculate_customer_balance(serializer.instance.sale.customer)

    def perform_destroy(self, instance):
        customer = instance.sale.customer
        super().perform_destroy(instance)  # logs + deletes
        recalculate_customer_balance(customer)
