"""Spreadsheet column-header vocabulary -> canonical invoice fields."""

from __future__ import annotations

import re

COLUMN_SYNONYMS: dict[str, list[str]] = {
    "invoice_number": [
        "invoice no", "invoice number", "invoice #", "invoice num", "inv no", "inv #", "inv number",
        "invoice id", "invoice", "bill no", "bill number", "document no", "doc no", "receipt no",
        "invoice ref", "reference no",
    ],
    "invoice_date": [
        "invoice date", "inv date", "date", "bill date", "issue date", "document date", "doc date",
        "date of issue", "receipt date",
    ],
    "supplier_name": [
        "supplier", "supplier name", "vendor", "vendor name", "seller", "seller name", "from",
        "company", "payee", "merchant",
    ],
    "customer_name": [
        "customer", "customer name", "client", "client name", "buyer", "buyer name", "bill to",
        "sold to", "billed to",
    ],
    "subtotal": [
        "subtotal", "sub total", "sub-total", "net amount", "net", "amount excl tax", "amount before tax",
        "taxable value", "taxable amount", "net total",
    ],
    "tax": ["tax", "vat", "gst", "tax amount", "vat amount", "gst amount", "sales tax", "total tax"],
    "total": [
        "total", "grand total", "total amount", "invoice total", "gross amount", "gross", "amount due",
        "total incl tax", "total due", "invoice amount", "total payable",
    ],
    "currency": ["currency", "ccy", "cur", "currency code"],
    "description": [
        "description", "item", "item description", "product", "product name", "service", "particulars",
        "details", "item name",
    ],
    "quantity": ["qty", "quantity", "units", "hours", "hrs", "qty.", "no of units"],
    "unit_price": ["unit price", "price", "rate", "unit cost", "price per unit", "unit rate"],
    "amount": ["line total", "line amount", "amount", "ext price", "extended price", "line value", "value"],
}

ALL_HEADER_WORDS = {syn for syns in COLUMN_SYNONYMS.values() for syn in syns}


def normalize_header(h: object) -> str:
    s = str(h or "").strip().lower()
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"[^a-z0-9# .]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s


def header_score(cell: object) -> int:
    """How strongly a cell looks like a known column header (0 = not at all)."""
    h = normalize_header(cell)
    if not h:
        return 0
    if h in ALL_HEADER_WORDS:
        return 3
    if any(re.search(rf"\b{re.escape(w)}\b", h) for w in ALL_HEADER_WORDS if len(w) > 3):
        return 1
    return 0
