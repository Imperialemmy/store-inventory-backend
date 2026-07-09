from django.db import models
from django.utils.timezone import now
from users.models import CustomUser


class CustomerTag(models.Model):
    """A reusable label for customers, e.g. VIP or Special Pricing."""
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Customer(models.Model):
    user = models.ForeignKey(CustomUser, related_name="customers", on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)

    tags = models.ManyToManyField(CustomerTag, related_name="customers", blank=True)
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "name", "phone_number")
        ordering = ["name"]

    def __str__(self):
        return self.name
