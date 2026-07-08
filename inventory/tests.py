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

    def test_create_and_list_products_alphabetically(self):
        self.client_api.post("/api/v1/products/", {"name": "Yam", "price": "500", "stock": 10}, format="json")
        self.client_api.post("/api/v1/products/", {"name": "Rice", "price": "1000", "stock": 20}, format="json")
        listed = self.client_api.get("/api/v1/products/").json()
        self.assertEqual(len(listed), 2)
        # plain array (unpaginated), ordered A–Z; the frontend filters client-side
        self.assertEqual([p["name"] for p in listed], ["Rice", "Yam"])

    def test_update_and_delete_product(self):
        created = self.client_api.post(
            "/api/v1/products/", {"name": "Garri", "price": "300", "stock": 8}, format="json").json()
        res = self.client_api.patch(
            f"/api/v1/products/{created['id']}/", {"price": "350", "stock": 12}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["stock"], 12)
        self.assertEqual(
            self.client_api.delete(f"/api/v1/products/{created['id']}/").status_code, 204)
        self.assertEqual(Product.objects.count(), 0)

    def test_product_str(self):
        product = Product.objects.create(name="Beans", price=Decimal("800"), stock=5)
        self.assertEqual(str(product), "Beans")
