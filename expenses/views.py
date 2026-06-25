from decimal import Decimal
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter

from api.views import AuditLogMixin, BulkDeleteMixin, CustomPagination
from users.permissions import IsAdminOrReadOnly
from sales.models import Sale
from .models import Expense, ExpenseCategory
from .serializers import ExpenseSerializer, ExpenseCategorySerializer


def _money(value):
    return str((value or Decimal("0")).quantize(Decimal("0.01")))


class ExpenseCategoryViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ["name"]


class ExpenseViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = Expense.objects.select_related("category", "supplier").all()
    serializer_class = ExpenseSerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["category", "payment_method", "supplier", "date"]
    search_fields = ["description", "reference"]
    ordering_fields = ["date", "amount", "created_at"]
    ordering = ["-date"]

    @action(detail=False, methods=["get"])
    def report(self, request):
        """Expense analytics + a simple profit & loss over a date range.

        Query params: start, end (YYYY-MM-DD).
        """
        expenses = Expense.objects.all()
        sales = Sale.objects.all()
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        if start:
            expenses = expenses.filter(date__gte=start)
            sales = sales.filter(date__gte=start)
        if end:
            expenses = expenses.filter(date__lte=end)
            sales = sales.filter(date__lte=end)

        total_expenses = expenses.aggregate(s=Sum("amount"))["s"] or Decimal("0")
        revenue = sales.aggregate(s=Sum("total"))["s"] or Decimal("0")

        spent_by_cat = {
            row["category"]: row["spent"]
            for row in expenses.values("category").annotate(spent=Sum("amount"))
        }
        by_category = [
            {
                "category": cat.name,
                "budget": _money(cat.monthly_budget),
                "spent": _money(spent_by_cat.get(cat.id, Decimal("0"))),
            }
            for cat in ExpenseCategory.objects.all()
        ]

        by_month = (
            expenses.annotate(bucket=TruncMonth("date"))
            .values("bucket")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("bucket")
        )

        return Response({
            "range": {"start": start, "end": end},
            "totals": {
                "expenses": _money(total_expenses),
                "revenue": _money(revenue),
                "profit": _money(revenue - total_expenses),
            },
            "by_category": by_category,
            "by_month": [
                {"bucket": row["bucket"], "total": _money(row["total"]), "count": row["count"]}
                for row in by_month
            ],
        })
