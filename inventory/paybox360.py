"""Readers and normalizers for the Paybox360 migration exports.

The workbook reader intentionally uses only Python's standard library.  The
Paybox export is a simple XLSX table and production should not need a large
spreadsheet dependency merely to run a one-time migration.
"""

from __future__ import annotations

import csv
import re
import zipfile
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from xml.etree import ElementTree


SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
QUARTER = Decimal("0.25")


def clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_decimal(value, label: str) -> Decimal:
    try:
        number = Decimal(clean_text(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} is not a valid number: {value!r}") from None
    if not number.is_finite():
        raise ValueError(f"{label} must be finite.")
    return number


def round_stock(value: Decimal, policy: str) -> Decimal:
    value = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if policy == "exact":
        return value
    units = value / QUARTER
    rounding = ROUND_HALF_UP if policy == "nearest-quarter" else ROUND_FLOOR
    return units.to_integral_value(rounding=rounding) * QUARTER


def _column_number(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    result = 0
    for character in letters.upper():
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def read_first_xlsx_sheet(path: str | Path) -> list[list[str]]:
    path = Path(path)
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Could not open inventory workbook {path}: {exc}") from exc

    with archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = ["".join(item.itertext()) for item in root]
        try:
            root = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        except KeyError as exc:
            raise ValueError("Inventory workbook has no first worksheet.") from exc

    rows: list[list[str]] = []
    for row in root.findall(f".//{{{SHEET_NS}}}sheetData/{{{SHEET_NS}}}row"):
        values: dict[int, str] = {}
        for cell in row.findall(f"{{{SHEET_NS}}}c"):
            index = _column_number(cell.attrib.get("r", "A1"))
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                value = "".join(cell.itertext())
            else:
                node = cell.find(f"{{{SHEET_NS}}}v")
                value = node.text if node is not None and node.text is not None else ""
                if cell_type == "s" and value:
                    value = shared_strings[int(value)]
            values[index] = clean_text(value)
        width = max(values, default=-1) + 1
        rows.append([values.get(index, "") for index in range(width)])
    return rows


@dataclass(frozen=True)
class ProductImportRow:
    name: str
    category: str
    stock: Decimal
    cost_price: Decimal
    price: Decimal


@dataclass(frozen=True)
class CustomerImportRow:
    legacy_id: str
    name: str
    phone_number: str
    email: str
    created_at: datetime | None


def read_inventory(path: str | Path, rounding: str = "exact"):
    rows = read_first_xlsx_sheet(path)
    expected = ["category", "subcategory", "item", "quantity", "stock price", "selling price"]
    header_index = next(
        (index for index, row in enumerate(rows) if [clean_text(v).casefold() for v in row[:6]] == expected),
        None,
    )
    if header_index is None:
        raise ValueError("Inventory workbook is missing the expected six-column header.")

    grouped: OrderedDict[str, list[ProductImportRow]] = OrderedDict()
    errors = []
    below_cost = []
    for source_row, values in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any(values):
            continue
        padded = values + [""] * (6 - len(values))
        category, _subcategory, name, quantity, cost_price, price = padded[:6]
        name = clean_text(name)
        category = clean_text(category)
        try:
            if not name:
                raise ValueError("item name is blank")
            if len(name) > 150:
                raise ValueError("item name exceeds 150 characters")
            if len(category) > 50:
                raise ValueError("category exceeds 50 characters")
            stock = parse_decimal(quantity, "quantity")
            cost = parse_decimal(cost_price, "stock price").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            selling = parse_decimal(price, "selling price").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if stock < 0 or cost < 0 or selling < 0:
                raise ValueError("quantity and prices cannot be negative")
        except ValueError as exc:
            errors.append({"row": source_row, "error": str(exc)})
            continue
        record = ProductImportRow(name, category, stock, cost, selling)
        grouped.setdefault(name.casefold(), []).append(record)
        if selling < cost:
            below_cost.append(name)

    products = []
    duplicates = []
    non_quarter = []
    for records in grouped.values():
        selected = records[-1]
        raw_stock = sum((record.stock for record in records), Decimal("0")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        if raw_stock % QUARTER:
            non_quarter.append({"name": selected.name, "stock": str(raw_stock)})
        products.append(ProductImportRow(
            name=selected.name,
            category=selected.category,
            stock=round_stock(raw_stock, rounding),
            cost_price=selected.cost_price,
            price=selected.price,
        ))
        if len(records) > 1:
            duplicates.append({
                "name": selected.name,
                "rows": len(records),
                "combined_stock": str(raw_stock),
                "categories": sorted({record.category for record in records}),
            })
    return products, {
        "source_rows": sum(len(records) for records in grouped.values()),
        "products": len(products),
        "duplicate_products": duplicates,
        "non_quarter_products": non_quarter,
        "selling_below_cost": sorted(set(below_cost)),
        "errors": errors,
    }


def read_customers(directory: str | Path, branch: str):
    directory = Path(directory)
    files = sorted(directory.glob("All_Customer_*"))
    if not files:
        raise ValueError(f"No All_Customer_* exports found in {directory}.")

    expected = {"created_at", "customer", "name", "email", "phone", "branch", "purchase_amount", "status"}
    records: OrderedDict[str, CustomerImportRow] = OrderedDict()
    source_rows = skipped_branch = 0
    duplicates = []
    errors = []
    for path in files:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not expected.issubset(set(reader.fieldnames or [])):
                raise ValueError(f"Customer export {path.name} has unexpected columns.")
            for source_row, row in enumerate(reader, start=2):
                source_rows += 1
                if clean_text(row.get("branch")).casefold() != branch.casefold():
                    skipped_branch += 1
                    continue
                legacy_id = clean_text(row.get("customer"))
                name = clean_text(row.get("name"))
                phone = clean_text(row.get("phone"))
                email = clean_text(row.get("email")).lower()
                if not legacy_id or not name:
                    errors.append({"file": path.name, "row": source_row, "error": "customer ID or name is blank"})
                    continue
                if len(legacy_id) > 64 or len(name) > 150 or len(phone) > 20:
                    errors.append({"file": path.name, "row": source_row, "error": "customer field exceeds the application limit"})
                    continue
                try:
                    created_at = datetime.fromisoformat(clean_text(row.get("created_at")))
                except ValueError:
                    created_at = None
                record = CustomerImportRow(legacy_id, name, phone, email, created_at)
                if legacy_id in records:
                    if records[legacy_id] != record:
                        duplicates.append({"legacy_id": legacy_id, "name": name, "conflicting": True})
                    continue
                records[legacy_id] = record
    return list(records.values()), {
        "files": [path.name for path in files],
        "source_rows": source_rows,
        "customers": len(records),
        "skipped_other_branches": skipped_branch,
        "duplicate_customer_ids": source_rows - skipped_branch - len(records) - len(errors),
        "conflicting_duplicates": duplicates,
        "errors": errors,
        "source_status_ignored": True,
        "purchase_amount_not_imported_as_debt": True,
    }
