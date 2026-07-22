import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    ADMIN = 'admin'
    SELLER = 'seller'
    ROLE_CHOICES = (
        (ADMIN, 'Admin'),
        (SELLER, 'Seller'),
    )
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=SELLER)
    # Rotated on every login; tokens carry it as the `sid` claim so only the
    # most recent login stays valid (one active session per account).
    session_id = models.UUIDField(default=uuid.uuid4, editable=False)
    def __str__(self):
        return self.username

    class Meta:
        app_label = "users"  # Ensures the app label is correctly used
