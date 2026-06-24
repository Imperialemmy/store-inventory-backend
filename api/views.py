from django.db.models import OuterRef, Subquery
from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from users.models import CustomUser
from .serializers import (
    BrandSerializer, CategorySerializer, SizeSerializer, WareSerializer,
    WareVariantSerializer, BatchSerializer, ImageSerializer, CustomUserSerializer,
    PromoteUserSerializer, SupplierSerializer, WarehouseSerializer, AuditLogSerializer,
)
from inventory.models import (
    Brand, Category, Size, Ware, WareVariant, Batch, Image,
    Supplier, Warehouse, AuditLog,
)
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from inventory.filters import WareFilter
from inventory.services import low_stock_variants
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from users.permissions import IsAdminOrReadOnly


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
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = BrandSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name']

class CategoryViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = Category.objects.all()
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = CategorySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name']

class SizeViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    permission_classes = [IsAdminOrReadOnly]
    queryset = Size.objects.all()
    serializer_class = SizeSerializer


class WareViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = Ware.objects.all()
    serializer_class = WareSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = WareFilter
    search_fields = ['name']
    permission_classes = [IsAdminOrReadOnly]


class SupplierViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name', 'contact_name', 'email']


class WarehouseViewSet(AuditLogMixin, ModelViewSet, BulkDeleteMixin):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name']


class WareVariantViewSet(AuditLogMixin, ModelViewSet):
    queryset = WareVariant.objects.all()
    serializer_class = WareVariantSerializer
    pagination_class = CustomPagination
    permission_classes = [IsAdminOrReadOnly]
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
    permission_classes = [IsAdminOrReadOnly]
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['variant', 'warehouse', 'supplier']

class ImageViewSet(AuditLogMixin, ModelViewSet):
    permission_classes = [IsAdminOrReadOnly]
    queryset = Image.objects.all()
    serializer_class = ImageSerializer


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