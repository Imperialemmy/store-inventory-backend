from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from users.models import CustomUser
from customers.models import Customer
from inventory.models import Product
from .models import Sale
from inventory.models import InventoryMovement


class SalesFlowTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="admin", email="a@a.com", password="x", role="admin")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.admin)
        self.product = Product.objects.create(name="Rice 50kg", price=Decimal("1000"), stock=25)
        self.customer = Customer.objects.create(user=self.admin, name="Buyer")

    def create_sale(self, quantity=8):
        return self.client_api.post("/api/v1/sales/", {
            "customer": self.customer.id,
            "items": [{"product": self.product.id, "quantity": quantity}],
        }, format="json")

    def test_sale_prices_from_product_and_computes_totals(self):
        res = self.create_sale(8)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(Decimal(data["items"][0]["unit_price"]), Decimal("1000.00"))
        self.assertEqual(Decimal(data["subtotal"]), Decimal("8000.00"))
        self.assertEqual(Decimal(data["vat_amount"]), Decimal("0.00"))  # prices are VAT-inclusive
        self.assertEqual(Decimal(data["total"]), Decimal("8000.00"))
        self.assertEqual(data["payment_status"], "pending")

    def test_stock_decrements(self):
        self.create_sale(8)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 17)

    def test_oversell_is_blocked_and_rolled_back(self):
        res = self.create_sale(9999)
        self.assertEqual(res.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 25)
        self.assertEqual(Sale.objects.count(), 0)

    def test_payment_updates_sale_balance(self):
        sale = self.create_sale(8).json()
        self.client_api.post("/api/v1/payments/", {
            "sale": sale["id"], "amount": "5000", "method": "transfer",
        }, format="json")
        detail = self.client_api.get(f"/api/v1/sales/{sale['id']}/").json()
        self.assertEqual(Decimal(detail["balance"]), Decimal("3000.00"))
        self.assertEqual(detail["payment_status"], "partial")

    def test_delete_sale_restores_stock(self):
        sale = self.create_sale(8).json()
        res = self.client_api.delete(f"/api/v1/sales/{sale['id']}/")
        self.assertEqual(res.status_code, 204)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 25)

    def test_credit_note_restocks_and_credits(self):
        sale = self.create_sale(10).json()
        item_id = sale["items"][0]["id"]
        res = self.client_api.post("/api/v1/credit-notes/", {
            "sale": sale["id"], "reason": "Damaged",
            "items": [{"sale_item": item_id, "quantity": 4}],
        }, format="json")
        self.assertEqual(res.status_code, 201)
        # 4 × 1000, no VAT
        self.assertEqual(Decimal(res.json()["amount"]), Decimal("4000.00"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 19)  # 25 - 10 + 4
        detail = self.client_api.get(f"/api/v1/sales/{sale['id']}/").json()
        self.assertEqual(Decimal(detail["amount_credited"]), Decimal("4000.00"))
        self.assertEqual(detail["items"][0]["returned_quantity"], 4)

    def test_delete_sale_with_returns_does_not_double_restock(self):
        sale = self.create_sale(10).json()  # stock 25 -> 15
        item_id = sale["items"][0]["id"]
        self.client_api.post("/api/v1/credit-notes/", {
            "sale": sale["id"], "items": [{"sale_item": item_id, "quantity": 4}],
        }, format="json")  # stock 15 -> 19
        res = self.client_api.delete(f"/api/v1/sales/{sale['id']}/")
        self.assertEqual(res.status_code, 204)
        self.product.refresh_from_db()
        # Only the 6 un-returned units come back: 19 + 6 = 25, not 29.
        self.assertEqual(self.product.stock, 25)

    def test_credit_note_over_return_blocked(self):
        sale = self.create_sale(10).json()
        item_id = sale["items"][0]["id"]
        self.client_api.post("/api/v1/credit-notes/", {
            "sale": sale["id"], "items": [{"sale_item": item_id, "quantity": 4}],
        }, format="json")
        res = self.client_api.post("/api/v1/credit-notes/", {
            "sale": sale["id"], "items": [{"sale_item": item_id, "quantity": 7}],
        }, format="json")
        self.assertEqual(res.status_code, 400)

    def test_offline_sale_sync_is_idempotent_with_atomic_payment(self):
        client_sale_id = "e57c6a88-1fa1-4c77-8ef1-87b386ba1fa2"
        payload = {
            "client_sale_id": client_sale_id,
            "customer": self.customer.id,
            "sold_at": "2026-07-11T09:15:00+01:00",
            "device_id": "mum-phone",
            "offline_created": True,
            "items": [{"product": self.product.id, "quantity": 3}],
            "initial_payment": {"amount": "3000.00", "method": "cash"},
        }
        first = self.client_api.post("/api/v1/sales/", payload, format="json")
        second = self.client_api.post("/api/v1/sales/", payload, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(Sale.objects.filter(client_sale_id=client_sale_id).count(), 1)
        sale = Sale.objects.get(client_sale_id=client_sale_id)
        self.assertEqual(sale.payments.count(), 1)
        self.assertEqual(
            InventoryMovement.objects.filter(sale=sale, reason=InventoryMovement.SALE).count(),
            1,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 22)

    def test_offline_sale_records_real_sale_and_flags_negative_stock(self):
        res = self.client_api.post("/api/v1/sales/", {
            "client_sale_id": "7e0c6f5f-dc70-444b-8ce5-26b935f667fc",
            "customer": self.customer.id,
            "offline_created": True,
            "device_id": "mum-phone",
            "items": [{"product": self.product.id, "quantity": 30}],
        }, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()["inventory_attention"])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, -5)
        movement = InventoryMovement.objects.get(sale_id=res.json()["id"])
        self.assertEqual(movement.quantity, -30)
        self.assertEqual(movement.stock_after, -5)

    def test_invalid_initial_payment_rolls_back_sale_stock_and_movement(self):
        res = self.client_api.post("/api/v1/sales/", {
            "client_sale_id": "294be58a-4499-4eb1-873d-ecc61acf50dd",
            "customer": self.customer.id,
            "offline_created": True,
            "items": [{"product": self.product.id, "quantity": 2}],
            "initial_payment": {"amount": "999999.00", "method": "cash"},
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Sale.objects.filter(
            client_sale_id="294be58a-4499-4eb1-873d-ecc61acf50dd"
        ).exists())
        self.assertEqual(InventoryMovement.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 25)

    def test_payment_rejects_zero_negative_and_overpayment(self):
        sale = self.create_sale(2).json()
        for amount in ("0", "-1", "999999"):
            res = self.client_api.post("/api/v1/payments/", {
                "sale": sale["id"], "amount": amount, "method": "cash",
            }, format="json")
            self.assertEqual(res.status_code, 400)

    def test_reused_client_id_with_different_payload_is_rejected(self):
        client_sale_id = "785cf1ca-d4d0-4d68-9e3c-ea57619bc0f6"
        first = self.client_api.post("/api/v1/sales/", {
            "client_sale_id": client_sale_id,
            "customer": self.customer.id,
            "offline_created": True,
            "items": [{"product": self.product.id, "quantity": 2}],
        }, format="json")
        second = self.client_api.post("/api/v1/sales/", {
            "client_sale_id": client_sale_id,
            "customer": self.customer.id,
            "offline_created": True,
            "items": [{"product": self.product.id, "quantity": 3}],
        }, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Sale.objects.filter(client_sale_id=client_sale_id).count(), 1)

    def test_reused_client_id_with_different_price_is_rejected(self):
        client_sale_id = "fc442d61-863b-4b56-9875-395ea633bdbf"
        base = {
            "client_sale_id": client_sale_id,
            "customer": self.customer.id,
            "offline_created": True,
            "items": [{
                "product": self.product.id, "quantity": 1, "unit_price": "1000.00",
            }],
        }
        first = self.client_api.post("/api/v1/sales/", base, format="json")
        changed = {
            **base,
            "items": [{
                "product": self.product.id, "quantity": 1, "unit_price": "900.00",
            }],
        }
        second = self.client_api.post("/api/v1/sales/", changed, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)

    def test_offline_stale_price_is_preserved_and_flagged(self):
        res = self.client_api.post("/api/v1/sales/", {
            "client_sale_id": "586e9416-f930-4ac5-b85c-d38cf471ac1d",
            "customer": self.customer.id,
            "offline_created": True,
            "items": [{
                "product": self.product.id,
                "quantity": 1,
                "unit_price": "900.00",
            }],
        }, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()["pricing_attention"])
        self.assertEqual(Decimal(res.json()["items"][0]["unit_price"]), Decimal("900.00"))

    def test_seller_cannot_override_current_price_online(self):
        seller = CustomUser.objects.create_user(
            username="price-seller", email="price@example.com",
            password="x", role="seller",
        )
        client = APIClient()
        client.force_authenticate(seller)
        res = client.post("/api/v1/sales/", {
            "customer": self.customer.id,
            "items": [{
                "product": self.product.id,
                "quantity": 1,
                "unit_price": "1.00",
            }],
        }, format="json")
        self.assertEqual(res.status_code, 400)

    def test_duplicate_product_lines_are_rejected_without_side_effects(self):
        res = self.client_api.post("/api/v1/sales/", {
            "customer": self.customer.id,
            "items": [
                {"product": self.product.id, "quantity": 1},
                {"product": self.product.id, "quantity": 2},
            ],
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(InventoryMovement.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 25)

    def test_offline_sale_and_payment_use_actual_lagos_sale_date(self):
        res = self.client_api.post("/api/v1/sales/", {
            "client_sale_id": "76592bce-9dfa-4c46-ae33-e3bf8cc20fcf",
            "customer": self.customer.id,
            "offline_created": True,
            # 23:30 UTC is already the following day in Lagos.
            "sold_at": "2026-07-10T23:30:00Z",
            "items": [{"product": self.product.id, "quantity": 1}],
            "initial_payment": {"amount": "1000.00", "method": "cash"},
        }, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["date"], "2026-07-11")
        self.assertEqual(res.json()["payments"][0]["date"], "2026-07-11")


class RolePermissionTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="admin2", email="a2@a.com", password="x", role="admin")
        self.seller = CustomUser.objects.create_user(
            username="seller2", email="s2@a.com", password="x", role="seller")

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_seller_can_create_customers_and_sales_not_products(self):
        client = self._client(self.seller)
        self.assertEqual(client.post("/api/v1/customers/", {
            "name": "C1"}, format="json").status_code, 201)
        # seller cannot create products (admin-only)
        self.assertEqual(client.post("/api/v1/products/", {
            "name": "P1", "price": "100", "stock": 5}, format="json").status_code, 403)
        # but can read them
        self.assertEqual(client.get("/api/v1/products/").status_code, 200)

    def test_admin_can_create_products(self):
        client = self._client(self.admin)
        self.assertEqual(client.post("/api/v1/products/", {
            "name": "P3", "price": "100", "stock": 5}, format="json").status_code, 201)

    def test_only_admin_can_list_users(self):
        self.assertEqual(self._client(self.seller).get("/api/v1/users/").status_code, 403)
        self.assertEqual(self._client(self.admin).get("/api/v1/users/").status_code, 200)

    def test_walk_in_customer_is_reused_not_duplicated(self):
        client = self._client(self.seller)
        first = client.get("/api/v1/customers/walk-in/")
        second = client.get("/api/v1/customers/walk-in/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["name"], "Walk-in Customer")
        # Same record returned every time — no duplicate walk-in customers.
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(Customer.objects.filter(name="Walk-in Customer").count(), 1)

    def test_walk_in_sale_cannot_be_pay_later(self):
        client = self._client(self.seller)
        walk_in = client.get("/api/v1/customers/walk-in/").json()
        product = Product.objects.create(name="Beans", price=Decimal("500"), stock=10)
        res = client.post("/api/v1/sales/", {
            "customer": walk_in["id"],
            "items": [{"product": product.id, "quantity": 1}],
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)

    def test_walk_in_sale_paid_in_full_is_accepted(self):
        client = self._client(self.seller)
        walk_in = client.get("/api/v1/customers/walk-in/").json()
        product = Product.objects.create(name="Oil", price=Decimal("1000"), stock=10)
        res = client.post("/api/v1/sales/", {
            "customer": walk_in["id"],
            "items": [{"product": product.id, "quantity": 1}],
            "initial_payment": {"amount": "1000.00", "method": "cash"},
        }, format="json")
        self.assertEqual(res.status_code, 201)
