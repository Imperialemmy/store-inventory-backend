from django.contrib import admin
from .models import Brand, Category, Size, Ware, WareVariant, Batch, Image

admin.site.register(Brand)
admin.site.register(Category)
admin.site.register(Size)
admin.site.register(Ware)
admin.site.register(WareVariant)
admin.site.register(Batch)
admin.site.register(Image)
