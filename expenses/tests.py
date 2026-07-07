from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from users.models import CustomUser
from .models import ExpenseCategory


class ExpenseTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username="exadmin", email="e@a.com", password="x", role="admin")
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.admin)
        self.category = ExpenseCategory.objects.create(
            name="Logistics", monthly_budget=Decimal("50000"))

    def test_expense_report_profit_and_budget(self):
        self.client_api.post("/api/v1/expenses/", {
            "category": self.category.id, "description": "Fuel",
            "amount": "15000", "payment_method": "cash",
        }, format="json")
        self.client_api.post("/api/v1/expenses/", {
            "category": self.category.id, "description": "Driver",
            "amount": "8000", "payment_method": "petty_cash",
        }, format="json")

        report = self.client_api.get("/api/v1/expenses/report/").json()
        self.assertEqual(report["totals"]["expenses"], "23000.00")
        # No sales in this test, so profit is negative expenses.
        self.assertEqual(report["totals"]["profit"], "-23000.00")
        row = report["by_category"][0]
        self.assertEqual(row["category"], "Logistics")
        self.assertEqual(row["spent"], "23000.00")
        self.assertEqual(row["budget"], "50000.00")

    def test_non_manager_cannot_write_expenses(self):
        user = CustomUser.objects.create_user(
            username="plain", email="p@a.com", password="x", role="user")
        client = APIClient()
        client.force_authenticate(user)
        res = client.post("/api/v1/expenses/", {
            "category": self.category.id, "description": "X", "amount": "10",
        }, format="json")
        self.assertEqual(res.status_code, 403)
