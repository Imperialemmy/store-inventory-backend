from django.db import models
from django.db.models import Sum
from users.models import CustomUser
from django.utils.timezone import now



class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Size(models.Model):
    size = models.CharField(max_length=10)
    size_unit = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return f'{self.size} {self.size_unit if self.size_unit else ""}'.strip()

class Ware(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    brand = models.ForeignKey(Brand, related_name='wares', on_delete=models.CASCADE)
    category = models.ForeignKey(Category, related_name='wares', on_delete=models.CASCADE)
    description = models.TextField(null=True, blank=True)
    size = models.ManyToManyField(Size, related_name='wares', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'name', 'brand')

    def __str__(self):
        return f"{self.name}"


class WareVariant(models.Model):
    ware = models.ForeignKey('Ware', related_name='variants', on_delete=models.CASCADE)
    size = models.ForeignKey('Size', on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_available = models.BooleanField(default=True)

    class Meta:
        unique_together = ('ware', 'size')

    def __str__(self):
        return f"{self.ware.name} - {self.size}"

    def update_availability(self):
        """ Update the availability based on stock count. """
        self.is_available = self.get_stock() > 0
        self.save()

    def get_stock(self):
        """ Efficiently calculate total stock for this variant. """
        stock = self.batches.aggregate(total=Sum('quantity'))['total']
        return stock or 0  # Return 0 if there are no batches



class Batch(models.Model):
    variant = models.ForeignKey(WareVariant, related_name='batches', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=0)
    expiry_date = models.DateField()
    manufacturing_date = models.DateField(null=True, blank=True)
    lot_number = models.CharField(max_length=50, blank=True, null=True)
    is_expired = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Batch {self.lot_number or 'N/A'} - {self.variant}"

    def save(self, *args, **kwargs):
        """ Update expiration status and variant availability when saving a batch. """
        self.is_expired = self.expiry_date < now().date()
        super().save(*args, **kwargs)
        self.variant.update_availability()  # Update WareVariant availability


class Image(models.Model):
    ware = models.ForeignKey(Ware, related_name='ware_images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='ware_images/')
    alt_text = models.CharField(max_length=255, blank=True, null=True)
    order = models.PositiveIntegerField(default=0)






