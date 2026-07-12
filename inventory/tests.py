from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import CustomUser
from .models import Product, InventoryMovement


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

    def test_duplicate_name_blocked_case_insensitively(self):
        self.client_api.post("/api/v1/products/", {"name": "Rice", "price": "1000", "stock": 5}, format="json")
        res = self.client_api.post("/api/v1/products/", {"name": "  rice ", "price": "900", "stock": 3}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("already exists", str(res.json()).lower())
        self.assertEqual(Product.objects.count(), 1)

    def test_product_str(self):
        product = Product.objects.create(name="Beans", price=Decimal("800"), stock=5)
        self.assertEqual(str(product), "Beans")

    def test_opening_stock_and_editor_correction_are_ledgered(self):
        created = self.client_api.post("/api/v1/products/", {
            "name": "Flour", "price": "500", "stock": 10,
        }, format="json").json()
        opening = InventoryMovement.objects.get(
            product_id=created["id"], reason=InventoryMovement.OPENING
        )
        self.assertEqual(opening.quantity, 10)
        self.assertEqual(opening.stock_after, 10)

        self.client_api.patch(
            f"/api/v1/products/{created['id']}/", {"stock": 7}, format="json"
        )
        correction = InventoryMovement.objects.get(
            product_id=created["id"], reason=InventoryMovement.CORRECTION
        )
        self.assertEqual(correction.quantity, -3)
        self.assertEqual(correction.stock_after, 7)

    def test_admin_can_record_restock_and_damage_adjustments(self):
        product = Product.objects.create(name="Oil", price=Decimal("100"), stock=5)
        restock = self.client_api.post("/api/v1/inventory-movements/", {
            "product": product.id,
            "quantity": 8,
            "reason": "restock",
            "note": "Supplier delivery",
        }, format="json")
        damage = self.client_api.post("/api/v1/inventory-movements/", {
            "product": product.id,
            "quantity": -2,
            "reason": "damage",
            "note": "Leaking packs",
        }, format="json")
        self.assertEqual(restock.status_code, 201)
        self.assertEqual(damage.status_code, 201)
        product.refresh_from_db()
        self.assertEqual(product.stock, 11)

    def test_product_deletion_keeps_ledger_history(self):
        created = self.client_api.post("/api/v1/products/", {
            "name": "Disposable item", "price": "10", "stock": 2,
        }, format="json").json()
        movement_id = InventoryMovement.objects.get(product_id=created["id"]).id
        self.assertEqual(
            self.client_api.delete(f"/api/v1/products/{created['id']}/").status_code,
            204,
        )
        movement = InventoryMovement.objects.get(id=movement_id)
        self.assertIsNone(movement.product_id)
