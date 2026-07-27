import csv
import io
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from customers.models import Customer
from inventory.models import InventoryMovement, Product
from users.models import CustomUser


def write_inventory(path: Path, rows):
    def cell(reference, value):
        if isinstance(value, (int, float)):
            return f'<c r="{reference}"><v>{value}</v></c>'
        return f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>'

    all_rows = [
        ["Akinfolu Foods"],
        ["Branch: Head Office"],
        ["Address"],
        ["Category", "Subcategory", "Item", "Quantity", "Stock Price", "Selling Price"],
        *rows,
    ]
    xml_rows = []
    for row_number, values in enumerate(all_rows, start=1):
        cells = "".join(cell(f"{chr(65 + index)}{row_number}", value) for index, value in enumerate(values))
        xml_rows.append(f'<row r="{row_number}">{cells}</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


class Paybox360ImportTests(TestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            username="admin", email="admin@example.com", password="test", role=CustomUser.ADMIN
        )

    def make_exports(self, directory: Path):
        inventory = directory / "branch_inventory.xlsx"
        write_inventory(inventory, [
            ["Tin Tomato", "N/A", "Gino Tomato", 1.25, 7000, 7400],
            ["Gb Foods", "N/A", "Gino Tomato", 3.25, 7100, 7500],
            ["Other", "N/A", "Legacy Fraction", 1.1, 1000, 1200],
        ])
        customer_file = directory / "All_Customer_test"
        with customer_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "created_at", "customer", "name", "email", "phone", "branch", "purchase_amount", "status"
            ])
            writer.writeheader()
            writer.writerow({
                "created_at": "2026-01-01 10:00:00+00:00", "customer": "legacy-1", "name": "Hope",
                "email": "hope@example.com", "phone": "08010000000", "branch": "Head Office",
                "purchase_amount": "50000", "status": "INACTIVE",
            })
            writer.writerow({
                "created_at": "2026-01-02 10:00:00+00:00", "customer": "legacy-2", "name": "Other Branch",
                "email": "", "phone": "08020000000", "branch": "Ayobo",
                "purchase_amount": "0", "status": "ACTIVE",
            })
        return inventory

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            inventory = self.make_exports(directory)
            output = io.StringIO()
            call_command(
                "import_paybox360", inventory=str(inventory), customers_dir=str(directory),
                owner=self.owner.username, stdout=output,
            )
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertIn("DRY RUN ONLY", output.getvalue())

    def test_commit_combines_duplicates_preserves_exact_stock_and_filters_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            inventory = self.make_exports(directory)
            call_command(
                "import_paybox360", inventory=str(inventory), customers_dir=str(directory),
                owner=self.owner.username, commit=True, stdout=io.StringIO(),
            )
        tomato = Product.objects.get(name="Gino Tomato")
        self.assertEqual(tomato.stock, 4.5)
        self.assertEqual(tomato.category, "Gb Foods")
        self.assertEqual(Product.objects.get(name="Legacy Fraction").stock, Decimal("1.1000"))
        customer = Customer.objects.get(legacy_id="legacy-1")
        self.assertEqual(customer.name, "Hope")
        self.assertTrue(customer.is_active)
        self.assertFalse(Customer.objects.filter(name="Other Branch").exists())
        self.assertEqual(InventoryMovement.objects.count(), 2)

    def test_same_file_is_idempotent_for_product_stock(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            inventory = self.make_exports(directory)
            options = {
                "inventory": str(inventory), "customers_dir": str(directory),
                "owner": self.owner.username, "commit": True, "allow_merge": True,
                "stdout": io.StringIO(),
            }
            call_command("import_paybox360", **options)
            product = Product.objects.get(name="Gino Tomato")
            product.stock = 4
            product.save(update_fields=["stock"])
            call_command("import_paybox360", **options)
        self.assertEqual(Product.objects.get(name="Gino Tomato").stock, 4)
        self.assertEqual(InventoryMovement.objects.count(), 2)
