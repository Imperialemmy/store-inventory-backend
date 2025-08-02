# inventory/filters.py
from django_filters import rest_framework as filters
from unicodedata import category

from .models import Ware

class WareFilter(filters.FilterSet):
    brand = filters.NumberFilter(field_name='brand__id')  # Filter by brand ID
    category = filters.NumberFilter(field_name='category__id')

    class Meta:
        model = Ware
        fields = ['brand','category']  # Add more filters later if needed