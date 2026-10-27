"""Internal extraction result shared by every extractor (rules, LLM, spreadsheet)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

SCALAR_FIELDS = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "customer_name",
    "subtotal",
    "tax",
    "total",
    "currency",
)
AMOUNT_FIELDS = ("subtotal", "tax", "total")
REQUIRED_FIELDS = ("invoice_number", "invoice_date", "supplier_name", "total")


class LineItemData(BaseModel):
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class InvoiceData(BaseModel):
    invoice_number: str | None = None
    invoice_date: date | None = None
    supplier_name: str | None = None
    customer_name: str | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = None
    line_items: list[LineItemData] = Field(default_factory=list)

    # Per-field confidence 0..1 and the source snippet that supports the value.
    confidence: dict[str, float] = Field(default_factory=dict)
    evidence: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    # Values the extractor proposed but that were rejected (e.g. not found in the source).
    rejected: dict[str, Any] = Field(default_factory=dict)
    method: str = "rules"
    model: str | None = None
    ambiguous_date: bool = False

    def set(self, field: str, value: Any, confidence: float, evidence: str | None = None) -> None:
        setattr(self, field, value)
        self.confidence[field] = round(float(confidence), 3)
        if evidence:
            self.evidence[field] = evidence.strip()[:300]

    def clear(self, field: str, reason: str) -> None:
        old = getattr(self, field)
        if old is not None:
            self.rejected[field] = str(old)
        setattr(self, field, None)
        self.confidence[field] = 0.0
        self.evidence.pop(field, None)
        self.notes.append(reason)
