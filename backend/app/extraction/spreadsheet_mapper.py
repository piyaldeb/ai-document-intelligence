"""Map tabular sheets (invoice registers, line-item exports) to invoice records.

Two shapes are recognised:
  * register: one row per invoice (invoice no, date, supplier, ..., total)
  * line-level export: several rows per invoice sharing the invoice number, each row a line item
Sheets that are neither (e.g. an invoice laid out as a form) return None and are handled
by the text extractors on the sheet's rendered text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.extraction.columns import COLUMN_SYNONYMS, normalize_header
from app.extraction.normalize import money, normalize_currency, parse_amount, parse_date
from app.extraction.schema import InvoiceData, LineItemData
from app.pipeline.types import SheetTable

STRUCTURED_CONFIDENCE = 0.98


@dataclass
class MappedInvoice:
    data: InvoiceData
    rows: list[int] = field(default_factory=list)  # 1-based spreadsheet row numbers


def map_columns(header: list[str]) -> dict[str, int]:
    """Assign each canonical field at most one column, strongest match first."""
    normalized = [normalize_header(h) for h in header]
    has_description = any(h in COLUMN_SYNONYMS["description"] for h in normalized)
    scored: list[tuple[int, str, int]] = []
    for col, h in enumerate(normalized):
        if not h:
            continue
        for field_name, synonyms in COLUMN_SYNONYMS.items():
            for syn in synonyms:
                if h == syn:
                    score = 100 + len(syn)
                elif len(syn) > 3 and re.search(rf"\b{re.escape(syn)}\b", h):
                    score = 50 + len(syn)
                else:
                    continue
                # "Amount" is a line amount in line-level exports and the invoice total otherwise.
                if syn == "amount" and field_name == "amount" and not has_description:
                    continue
                if syn == "amount" and field_name == "total":
                    continue
                scored.append((score, field_name, col))
    if not has_description:
        for col, h in enumerate(normalized):
            if h == "amount":
                scored.append((90, "total", col))
    scored.sort(reverse=True)
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for _score, field_name, col in scored:
        if field_name in mapping or col in used:
            continue
        mapping[field_name] = col
        used.add(col)
    return mapping


def _cell(row: list[Any], idx: int | None) -> Any:
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def _text(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def map_sheet(table: SheetTable, currency_hint: str | None = None) -> list[MappedInvoice] | None:
    if not table.header:
        return None
    cols = map_columns(table.header)
    is_register = "invoice_number" in cols and ("total" in cols or "amount" in cols or "subtotal" in cols)
    is_rowwise = "total" in cols and ("supplier_name" in cols or "invoice_date" in cols)
    if not (is_register or is_rowwise):
        return None

    groups: dict[str, MappedInvoice] = {}
    order: list[str] = []
    for offset, row in enumerate(table.rows):
        row_no = table.first_data_row + offset
        inv_no = _text(_cell(row, cols.get("invoice_number")))
        if "invoice_number" in cols and not inv_no:
            if order and "description" in cols and _cell(row, cols.get("description")) is not None:
                inv_no = order[-1]  # continuation line of the previous invoice
            elif not any(c is not None for c in row):
                continue
        key = inv_no or f"row-{row_no}"
        if key not in groups:
            groups[key] = MappedInvoice(InvoiceData(method="spreadsheet"))
            order.append(key)
        mapped = groups[key]
        mapped.rows.append(row_no)
        data = mapped.data

        def put(field_name: str, value: Any, data: InvoiceData = data, row_no: int = row_no) -> None:
            if value is not None and getattr(data, field_name) is None:
                data.set(field_name, value, STRUCTURED_CONFIDENCE, f"{table.name}!row {row_no}")

        put("invoice_number", inv_no)
        raw_currency = _cell(row, cols.get("currency"))
        currency = normalize_currency(raw_currency) if raw_currency is not None else None
        put("currency", currency)
        dayfirst = (currency or currency_hint) != "USD"
        raw_date = _cell(row, cols.get("invoice_date"))
        if raw_date is not None:
            parsed = parse_date(raw_date, dayfirst=dayfirst)
            if parsed is None:
                data.notes.append(f"row {row_no}: unparseable date {raw_date!r}")
                data.rejected["invoice_date"] = str(raw_date)
            put("invoice_date", parsed)
        put("supplier_name", _text(_cell(row, cols.get("supplier_name"))))
        put("customer_name", _text(_cell(row, cols.get("customer_name"))))
        for f in ("subtotal", "tax", "total"):
            raw = _cell(row, cols.get(f))
            if raw is None:
                continue
            val = parse_amount(raw)
            if val is None:
                data.notes.append(f"row {row_no}: non-numeric {f} {raw!r}")
                data.rejected[f] = str(raw)
            put(f, money(val))

        if "description" in cols:
            desc = _text(_cell(row, cols.get("description")))
            qty = parse_amount(_cell(row, cols.get("quantity")))
            unit = parse_amount(_cell(row, cols.get("unit_price")))
            amt = parse_amount(_cell(row, cols.get("amount")))
            if desc or amt is not None:
                data.line_items.append(LineItemData(description=desc, quantity=qty, unit_price=unit, amount=money(amt)))

    result = []
    for key in order:
        m = groups[key]
        if m.data.line_items:
            m.data.confidence["line_items"] = STRUCTURED_CONFIDENCE
        for f in ("invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency"):
            m.data.confidence.setdefault(f, 0.0)
        result.append(m)
    return result
