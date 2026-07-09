from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from users.permissions import AdminWriteOrReadOnly, SellerWriteOrReadOnly
from inventory.models import Product, AuditLog
from customers.models import Customer
from .serializers import ProductSerializer, CustomerSerializer


class AuditLogMixin:
    """Write an AuditLog row whenever a viewset creates, updates or deletes.

    The trail is internal (readable in the Django admin); there is no API
    endpoint for it.
    """

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


class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })


class ProductViewSet(AuditLogMixin, ModelViewSet):
    """Products: full CRUD. Returned unpaginated, A–Z (model ordering);
    the frontend filters client-side."""
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [AdminWriteOrReadOnly]


class CustomerViewSet(AuditLogMixin, ModelViewSet):
    """Customers: full CRUD, paginated (?page_size=N)."""
    WALK_IN_NAME = "Walk-in Customer"

    queryset = Customer.objects.prefetch_related("tags").all()
    serializer_class = CustomerSerializer
    permission_classes = [SellerWriteOrReadOnly]
    pagination_class = CustomPagination

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
