from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from customers.models import Customer
from inventory.models import Product
from sales.models import CreditNote, Payment, Refund, Sale
from users.models import CustomUser

from .realtime import publish_change


def after_commit(resources, source):
    transaction.on_commit(lambda: publish_change(resources, source))


@receiver([post_save, post_delete], sender=Product)
def product_changed(sender, instance, **kwargs):
    after_commit(["products", "operations", "notifications"], "product")


@receiver([post_save, post_delete], sender=Customer)
def customer_changed(sender, instance, **kwargs):
    after_commit(["customers"], "customer")


@receiver([post_save, post_delete], sender=Sale)
def sale_changed(sender, instance, **kwargs):
    after_commit(["sales", "operations", "notifications"], "sale")


@receiver([post_save, post_delete], sender=Payment)
def payment_changed(sender, instance, **kwargs):
    after_commit(["sales", "operations", "notifications"], "payment")


@receiver([post_save, post_delete], sender=Refund)
def refund_changed(sender, instance, **kwargs):
    after_commit(["sales", "operations", "notifications"], "refund")


@receiver([post_save, post_delete], sender=CreditNote)
def return_changed(sender, instance, **kwargs):
    after_commit(["sales", "products", "operations", "notifications"], "return")


@receiver([post_save, post_delete], sender=CustomUser)
def team_changed(sender, instance, **kwargs):
    after_commit(["team"], "team")
