"""Grounding check: every value an LLM returns must be traceable to the source text.

Values that cannot be found in the document are removed (set to None) and recorded in
`InvoiceData.rejected`, so a hallucinated invoice number or amount never reaches the
database as if it were extracted. Validation then flags the record for review.
"""

from __future__ import annotations

import re
from decimal import Decimal

from rapidfuzz import fuzz

from app.extraction.normalize import (
    DOLLAR_PREFIXES,
    SYMBOLS,
    detect_decimal_comma,
    find_amounts,
    find_dates,
    normalize_text_for_match,
)
from app.extraction.schema import InvoiceData


class SourceIndex:
    def __init__(self, text: str):
        self.text = text
        self.lower = re.sub(r"\s+", " ", text.lower())
        self.alnum = normalize_text_for_match(text)
        dc = detect_decimal_comma(text)
        self.amounts = {abs(a.value) for a in find_amounts(text, dc)}
        # Amounts may also be printed with the other convention in mixed documents.
        self.amounts |= {abs(a.value) for a in find_amounts(text, not dc)}
        self.dates = {d.value for d in find_dates(text, dayfirst=True)} | {
            d.value for d in find_dates(text, dayfirst=False)
        }

    def has_identifier(self, value: str) -> bool:
        norm = normalize_text_for_match(value)
        return bool(norm) and norm in self.alnum

    def has_name(self, value: str) -> bool:
        v = re.sub(r"\s+", " ", value.lower()).strip()
        if not v:
            return False
        if v in self.lower:
            return True
        return fuzz.partial_ratio(v, self.lower) >= 90

    def has_amount(self, value: Decimal) -> bool:
        target = abs(value)
        return any(abs(target - a) <= Decimal("0.005") for a in self.amounts)

    def has_date(self, value) -> bool:
        return value in self.dates

    def has_currency(self, code: str) -> bool:
        if re.search(rf"\b{code}\b", self.text):
            return True
        symbols = [s for s, c in SYMBOLS.items() if c == code] + [p for p, c in DOLLAR_PREFIXES.items() if c == code]
        if code == "USD":
            symbols.append("$")
        if code == "INR":
            symbols.append("Rs")
        if code == "BDT":
            symbols.append("Tk")
        return any(s in self.text for s in symbols)


def ground(data: InvoiceData, source: str) -> InvoiceData:
    idx = SourceIndex(source)
    checks = {
        "invoice_number": lambda v: idx.has_identifier(v),
        "supplier_name": lambda v: idx.has_name(v),
        "customer_name": lambda v: idx.has_name(v),
        "subtotal": lambda v: idx.has_amount(v),
        "tax": lambda v: idx.has_amount(v),
        "total": lambda v: idx.has_amount(v),
        "invoice_date": lambda v: idx.has_date(v),
        "currency": lambda v: idx.has_currency(v),
    }
    for field, check in checks.items():
        value = getattr(data, field)
        if value is not None and not check(value):
            data.clear(field, f"{field} value {value!s} was not found in the document text and was discarded")
    dropped = 0
    for item in data.line_items:
        if item.amount is not None and not idx.has_amount(item.amount):
            item.amount = None
            dropped += 1
    if dropped:
        data.notes.append(f"{dropped} line item amount(s) not found in the document were discarded")
    return data
