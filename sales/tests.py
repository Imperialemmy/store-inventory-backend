from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from users.models import CustomUser
from customers.models import Customer
from inventory.models import Product
from .models import Sale


class SalesFlowTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="admin", email="a@a.com", password="x", role="admin")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.admin)
        self.product = Product.objects.create(name="Rice 50kg", price=Decimal("1000"), stock=25)
        self.customer = Customer.objects.create(
            user=self.admin, name="Buyer", customer_type="retail", credit_limit=Decimal("1000000"))

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
        self.assertEqual(Decimal(data["vat_amount"]), Decimal("600.00"))  # 7.5%
        self.assertEqual(Decimal(data["total"]), Decimal("8600.00"))
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

    def test_payment_updates_balance_and_customer(self):
        sale = self.create_sale(8).json()
        self.client_api.post("/api/v1/payments/", {
            "sale": sale["id"], "amount": "5000", "method": "transfer",
        }, format="json")
        detail = self.client_api.get(f"/api/v1/sales/{sale['id']}/").json()
        self.assertEqual(Decimal(detail["balance"]), Decimal("3600.00"))
        self.assertEqual(detail["payment_status"], "partial")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.outstanding_balance, Decimal("3600.00"))

    def test_delete_sale_restores_stock_and_balance(self):
        sale = self.create_sale(8).json()
        res = self.client_api.delete(f"/api/v1/sales/{sale['id']}/")
        self.assertEqual(res.status_code, 204)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 25)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.outstanding_balance, Decimal("0.00"))

    def test_credit_note_restocks_and_credits(self):
        sale = self.create_sale(10).json()
        item_id = sale["items"][0]["id"]
        res = self.client_api.post("/api/v1/credit-notes/", {
            "sale": sale["id"], "reason": "Damaged",
            "items": [{"sale_item": item_id, "quantity": 4}],
        }, format="json")
        self.assertEqual(res.status_code, 201)
        # 4 × 1000 × 1.075 = 4300
        self.assertEqual(Decimal(res.json()["amount"]), Decimal("4300.00"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 19)  # 25 - 10 + 4
        detail = self.client_api.get(f"/api/v1/sales/{sale['id']}/").json()
        self.assertEqual(Decimal(detail["amount_credited"]), Decimal("4300.00"))
        self.assertEqual(detail["items"][0]["returned_quantity"], 4)

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


class RolePermissionTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="admin2", email="a2@a.com", password="x", role="admin")
        self.sales_user = CustomUser.objects.create_user(
            username="sales2", email="s2@a.com", password="x", role="sales")
        self.plain = CustomUser.objects.create_user(
            username="plain", email="p@a.com", password="x", role="user")

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_sales_role_can_create_customers_not_products(self):
        client = self._client(self.sales_user)
        self.assertEqual(client.post("/api/v1/customers/", {
            "name": "C1", "customer_type": "retail"}, format="json").status_code, 201)
        self.assertEqual(client.post("/api/v1/products/", {
            "name": "P1", "price": "100", "stock": 5}, format="json").status_code, 403)

    def test_plain_user_cannot_create_products(self):
        client = self._client(self.plain)
        self.assertEqual(client.post("/api/v1/products/", {
            "name": "P2", "price": "100", "stock": 5}, format="json").status_code, 403)

    def test_admin_can_create_products(self):
        client = self._client(self.admin)
        self.assertEqual(client.post("/api/v1/products/", {
            "name": "P3", "price": "100", "stock": 5}, format="json").status_code, 201)
