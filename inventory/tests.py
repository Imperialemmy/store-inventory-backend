from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import CustomUser
from .models import Product


class ProductTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="padmin", email="p@a.com", password="x", role="admin")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.admin)

    def test_create_and_search_products(self):
        self.client_api.post("/api/v1/products/", {"name": "Yam", "price": "500", "stock": 10}, format="json")
        self.client_api.post("/api/v1/products/", {"name": "Rice", "price": "1000", "stock": 20}, format="json")
        listed = self.client_api.get("/api/v1/products/").json()
        self.assertEqual(len(listed), 2)
        # default ordering is alphabetical
        self.assertEqual(listed[0]["name"], "Rice")
        found = self.client_api.get("/api/v1/products/?search=yam").json()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["name"], "Yam")

    def test_product_str(self):
        product = Product.objects.create(name="Beans", price=Decimal("800"), stock=5)
        self.assertEqual(str(product), "Beans")
