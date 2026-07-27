from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from customers.models import Customer
from inventory.models import InventoryMovement, Product
from inventory.paybox360 import read_customers, read_inventory
from sales.models import Sale


class Command(BaseCommand):
    help = "Dry-run or import Head Office products and customers from Paybox360 exports."

    def add_arguments(self, parser):
        parser.add_argument("--inventory", required=True, help="Path to branch_inventory_*.xlsx")
        parser.add_argument("--customers-dir", required=True, help="Directory containing All_Customer_* exports")
        parser.add_argument("--owner", required=True, help="Username or email that owns imported customers")
        parser.add_argument("--branch", default="Head Office")
        parser.add_argument(
            "--stock-rounding",
            choices=["exact", "nearest-quarter", "down-quarter"],
            default="exact",
            help="How to handle legacy stock that is not an exact quarter (default: preserve exactly).",
        )
        parser.add_argument("--commit", action="store_true", help="Write the import. Without this flag the command is read-only.")
        parser.add_argument("--allow-merge", action="store_true", help="Allow commit into a database containing operational records.")
        parser.add_argument("--report", help="Optional path for the JSON reconciliation report.")

    def handle(self, *args, **options):
        inventory_path = Path(options["inventory"]).expanduser().resolve()
        customers_dir = Path(options["customers_dir"]).expanduser().resolve()
        if not inventory_path.is_file():
            raise CommandError(f"Inventory file not found: {inventory_path}")
        if not customers_dir.is_dir():
            raise CommandError(f"Customer directory not found: {customers_dir}")

        user_model = get_user_model()
        try:
            owner = user_model.objects.get(
                Q(username__iexact=options["owner"]) | Q(email__iexact=options["owner"])
            )
        except user_model.DoesNotExist as exc:
            raise CommandError(f"No user found for {options['owner']!r}.") from exc
        except user_model.MultipleObjectsReturned as exc:
            raise CommandError("Owner matched more than one account; use the exact username.") from exc

        try:
            products, inventory_report = read_inventory(inventory_path, options["stock_rounding"])
            customers, customer_report = read_customers(customers_dir, options["branch"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        invalid_emails = []
        for customer in customers:
            if not customer.email:
                continue
            try:
                validate_email(customer.email)
            except ValidationError:
                invalid_emails.append({"legacy_id": customer.legacy_id, "email": customer.email})
        customer_report["invalid_emails_cleared"] = invalid_emails

        file_hash = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
        existing = {
            "products": Product.objects.count(),
            "customers": Customer.objects.exclude(name__iexact="Walk-in Customer").count(),
            "sales": Sale.objects.count(),
        }
        report = {
            "mode": "commit" if options["commit"] else "dry-run",
            "branch": options["branch"],
            "owner": owner.username,
            "stock_rounding": options["stock_rounding"],
            "inventory_sha256": file_hash,
            "inventory": inventory_report,
            "customers": customer_report,
            "existing_database": existing,
        }

        if inventory_report["errors"] or customer_report["errors"]:
            self._write_report(report, options.get("report"))
            raise CommandError("Source validation failed. Review the report; nothing was imported.")

        if not options["commit"]:
            self._write_report(report, options.get("report"))
            self.stdout.write(json.dumps(report, indent=2, default=str))
            self.stdout.write(self.style.WARNING("DRY RUN ONLY — rerun with --commit after reviewing the report."))
            return

        if any(existing.values()) and not options["allow_merge"]:
            self._write_report(report, options.get("report"))
            raise CommandError(
                "The database already contains products, customers, or sales. "
                "Nothing was imported; use --allow-merge only after taking a backup and reviewing the dry run."
            )

        imported = self._commit(products, customers, owner, file_hash, invalid_emails)
        report["result"] = imported
        self._write_report(report, options.get("report"))
        self.stdout.write(json.dumps(report, indent=2, default=str))
        self.stdout.write(self.style.SUCCESS("Paybox360 import completed successfully."))

    @transaction.atomic
    def _commit(self, products, customers, owner, file_hash, invalid_emails):
        invalid_email_ids = {row["legacy_id"] for row in invalid_emails}
        result = {
            "products_created": 0,
            "products_updated": 0,
            "products_skipped_as_already_imported": 0,
            "customers_created": 0,
            "customers_updated": 0,
        }
        existing_products = {product.name.casefold(): product for product in Product.objects.select_for_update()}
        for row in products:
            key = row.name.casefold()
            marker = f"paybox360:{file_hash[:16]}:{hashlib.sha1(key.encode()).hexdigest()[:16]}"
            if InventoryMovement.objects.filter(client_reference=marker).exists():
                result["products_skipped_as_already_imported"] += 1
                continue
            product = existing_products.get(key)
            created = product is None
            previous_stock = Decimal("0") if created else product.stock
            if created:
                product = Product(name=row.name)
            product.category = row.category
            product.price = row.price
            product.cost_price = row.cost_price
            product.stock = row.stock
            product.save()
            existing_products[key] = product
            InventoryMovement.objects.create(
                product=product,
                user=owner,
                quantity=row.stock - previous_stock,
                stock_after=row.stock,
                reason=InventoryMovement.OPENING if created else InventoryMovement.CORRECTION,
                client_reference=marker,
                event_at=now(),
                synced_at=now(),
                note="Paybox360 Head Office opening-data import.",
            )
            result["products_created" if created else "products_updated"] += 1

        for row in customers:
            defaults = {
                "user": owner,
                "name": row.name,
                "phone_number": row.phone_number or None,
                "email": None if row.legacy_id in invalid_email_ids else (row.email or None),
                "is_active": True,
                "notes": "Imported from Paybox360 Head Office export.",
            }
            customer = Customer.objects.filter(legacy_id=row.legacy_id).first()
            created = customer is None
            if customer is None:
                customer = Customer(legacy_id=row.legacy_id)
            for field, value in defaults.items():
                setattr(customer, field, value)
            if created and row.created_at is not None:
                customer.created_at = row.created_at
            customer.save()
            result["customers_created" if created else "customers_updated"] += 1
        return result

    @staticmethod
    def _write_report(report, report_path):
        if not report_path:
            return
        path = Path(report_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
