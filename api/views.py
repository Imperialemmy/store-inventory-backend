from django.db.models import OuterRef, Subquery
from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from users.models import CustomUser
from .serializers import BrandSerializer, CategorySerializer, SizeSerializer, WareSerializer, WareVariantSerializer, BatchSerializer, ImageSerializer,CustomUserSerializer
from inventory.models import Brand, Category, Size, Ware, WareVariant, Batch, Image
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from inventory.filters import WareFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from users.permissions import IsAdminOrReadOnly



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


class BrandViewSet(ModelViewSet, BulkDeleteMixin):
    queryset = Brand.objects.all()
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = BrandSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name']

class CategoryViewSet(ModelViewSet, BulkDeleteMixin):
    queryset = Category.objects.all()
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = CategorySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name']
    
class SizeViewSet(ModelViewSet, BulkDeleteMixin):
    permission_classes = [IsAdminOrReadOnly]
    queryset = Size.objects.all()
    serializer_class = SizeSerializer


class WareViewSet(ModelViewSet, BulkDeleteMixin):
    queryset = Ware.objects.all()
    serializer_class = WareSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = WareFilter
    search_fields = ['name']
    permission_classes = [IsAdminOrReadOnly]


class WareVariantViewSet(ModelViewSet):
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

class BatchViewSet(ModelViewSet):
    permission_classes = [IsAdminOrReadOnly]
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer

class ImageViewSet(ModelViewSet):
    permission_classes = [IsAdminOrReadOnly]
    queryset = Image.objects.all()
    serializer_class = ImageSerializer

class UserViewSet(ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = CustomUserSerializer