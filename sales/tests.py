from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from users.models import CustomUser
from customers.models import Customer
from inventory.models import Brand, Category, Size, Ware, WareVariant, Batch
from inventory.services import receive_stock
from .models import Sale


def make_catalog(user, retail="1000", wholesale="850", reorder=0):
    brand = Brand.objects.create(name="TestBrand")
    category = Category.objects.create(name="TestCat")
    size = Size.objects.create(size="50", size_unit="kg")
    ware = Ware.objects.create(user=user, name="Rice", brand=brand, category=category)
    ware.size.add(size)
    return WareVariant.objects.create(
        ware=ware, size=size,
        retail_price=Decimal(retail), wholesale_price=Decimal(wholesale),
        reorder_point=reorder,
    )


class SalesFlowTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="admin", email="a@a.com", password="x", role="admin")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.admin)
        self.variant = make_catalog(self.admin)
        # Two batches: earliest expiry must be drained first (FIFO).
        receive_stock(self.variant, 5, date.today() + timedelta(days=10), "L1")
        receive_stock(self.variant, 20, date.today() + timedelta(days=40), "L2")
        self.customer = Customer.objects.create(
            user=self.admin, name="Wholesale Buyer",
            customer_type="wholesale", credit_limit=Decimal("1000000"))

    def create_sale(self, quantity=8):
        return self.client_api.post("/api/v1/sales/", {
            "customer": self.customer.id,
            "items": [{"variant": self.variant.id, "quantity": quantity}],
        }, format="json")

    def test_sale_uses_wholesale_price_and_computes_totals(self):
        res = self.create_sale(8)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(Decimal(data["items"][0]["unit_price"]), Decimal("850.00"))
        self.assertEqual(Decimal(data["subtotal"]), Decimal("6800.00"))
        self.assertEqual(Decimal(data["vat_amount"]), Decimal("510.00"))  # 7.5%
        self.assertEqual(Decimal(data["total"]), Decimal("7310.00"))
        self.assertEqual(data["payment_status"], "pending")

    def test_stock_decrements_fifo_by_expiry(self):
        self.create_sale(8)
        batches = list(Batch.objects.filter(variant=self.variant)
                       .order_by("expiry_date").values_list("lot_number", "quantity"))
        self.assertEqual(batches, [("L1", 0), ("L2", 17)])
        self.assertEqual(self.variant.get_stock(), 17)

    def test_oversell_is_blocked_and_rolled_back(self):
        res = self.create_sale(9999)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.variant.get_stock(), 25)
        self.assertEqual(Sale.objects.count(), 0)

    def test_payment_updates_balance_and_customer(self):
        sale = self.create_sale(8).json()
        self.client_api.post("/api/v1/payments/", {
            "sale": sale["id"], "amount": "5000", "method": "transfer",
        }, format="json")
        detail = self.client_api.get(f"/api/v1/sales/{sale['id']}/").json()
        self.assertEqual(Decimal(detail["balance"]), Decimal("2310.00"))
        self.assertEqual(detail["payment_status"], "partial")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.outstanding_balance, Decimal("2310.00"))

    def test_delete_sale_restores_stock_and_balance(self):
        sale = self.create_sale(8).json()
        res = self.client_api.delete(f"/api/v1/sales/{sale['id']}/")
        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.variant.get_stock(), 25)
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
        # 4 × 850 × 1.075 = 3655
        self.assertEqual(Decimal(res.json()["amount"]), Decimal("3655.00"))
        self.assertEqual(self.variant.get_stock(), 19)
        detail = self.client_api.get(f"/api/v1/sales/{sale['id']}/").json()
        self.assertEqual(Decimal(detail["amount_credited"]), Decimal("3655.00"))
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

    def test_sales_report_totals(self):
        self.create_sale(8)
        report = self.client_api.get("/api/v1/sales/report/").json()
        self.assertEqual(report["totals"]["sales"], "7310.00")
        self.assertEqual(report["totals"]["invoices"], 1)
        self.assertEqual(report["top_products"][0]["quantity"], 8)

    def test_debt_aging_buckets(self):
        sale = self.create_sale(8).json()
        Sale.objects.filter(id=sale["id"]).update(date=date.today() - timedelta(days=45))
        aging = self.client_api.get("/api/v1/customers/debt-aging/").json()
        row = aging["results"][0]
        self.assertEqual(row["31_60"], "7310.00")
        self.assertEqual(row["0_30"], "0.00")


class RolePermissionTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="admin2", email="a2@a.com", password="x", role="admin")
        self.sales_user = CustomUser.objects.create_user(
            username="sales2", email="s2@a.com", password="x", role="sales")
        self.warehouse_user = CustomUser.objects.create_user(
            username="wh2", email="w2@a.com", password="x", role="warehouse")
        self.variant = make_catalog(self.admin)

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_sales_role_can_create_customers_not_brands(self):
        client = self._client(self.sales_user)
        self.assertEqual(client.post("/api/v1/customers/", {
            "name": "C1", "customer_type": "retail"}, format="json").status_code, 201)
        self.assertEqual(client.post("/api/v1/brands/", {"name": "B1"},
                                     format="json").status_code, 403)

    def test_warehouse_role_can_create_batches_not_brands(self):
        client = self._client(self.warehouse_user)
        res = client.post("/api/v1/batches/", {
            "variant": self.variant.id, "quantity": 5,
            "expiry_date": str(date.today() + timedelta(days=90)),
            "lot_number": "LX",
        }, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(client.post("/api/v1/brands/", {"name": "B2"},
                                     format="json").status_code, 403)

    def test_notifications_include_low_stock(self):
        self.variant.reorder_point = 10
        self.variant.save()
        client = self._client(self.admin)
        data = client.get("/api/v1/notifications/").json()
        self.assertTrue(any(i["type"] == "low_stock" for i in data["items"]))
