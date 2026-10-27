"""Business validation rules for extracted invoices.

Pure functions: given an invoice (+ context such as known duplicates) return issues.
Severity:
  error   -> data is missing or arithmetically inconsistent; the record must be reviewed
  warning -> plausible but suspicious; the record is flagged for review
  info    -> recorded for audit only
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.config import get_settings
from app.extraction.normalize import CURRENCY_CODES

FIELD_LABELS = {
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice date",
    "supplier_name": "Supplier name",
    "customer_name": "Customer name",
    "subtotal": "Subtotal",
    "tax": "Tax",
    "total": "Total",
    "currency": "Currency",
}
REQUIRED = ("invoice_number", "invoice_date", "supplier_name", "total")
RECOMMENDED = ("customer_name", "currency", "subtotal", "tax")


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    field: str | None = None
    details: dict[str, Any] = dc_field(default_factory=dict)


@dataclass
class InvoiceView:
    """The minimal shape validation needs (works for ORM rows and extraction results)."""

    invoice_number: str | None
    invoice_date: date | None
    supplier_name: str | None
    customer_name: str | None
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal | None
    currency: str | None
    line_items: list[dict[str, Decimal | None]]
    confidence: dict[str, float] = dc_field(default_factory=dict)
    rejected: dict[str, Any] = dc_field(default_factory=dict)
    notes: list[str] = dc_field(default_factory=list)
    ambiguous_date: bool = False
    min_ocr_confidence: float | None = None
    document_type: str = "invoice"


@dataclass
class DuplicateContext:
    exact: list[dict[str, Any]] = dc_field(default_factory=list)  # same supplier + invoice number
    probable: list[dict[str, Any]] = dc_field(default_factory=list)  # same supplier/date/total, other number


def _close(a: Decimal, b: Decimal) -> bool:
    s = get_settings()
    tol = max(Decimal(str(s.amount_tolerance_abs)), abs(b) * Decimal(str(s.amount_tolerance_rel)))
    return abs(a - b) <= tol


def validate(inv: InvoiceView, dup: DuplicateContext | None = None, today: date | None = None) -> list[Issue]:
    s = get_settings()
    today = today or date.today()
    issues: list[Issue] = []

    # 1. Missing fields ------------------------------------------------------------
    for f in REQUIRED:
        if getattr(inv, f) in (None, ""):
            extra = {"rejected_value": inv.rejected[f]} if f in inv.rejected else {}
            issues.append(Issue("MISSING_FIELD", "error", f"{FIELD_LABELS[f]} is missing", f, extra))
    for f in RECOMMENDED:
        if getattr(inv, f) in (None, ""):
            extra = {"rejected_value": inv.rejected[f]} if f in inv.rejected else {}
            # Receipts legitimately omit customer/subtotal/tax; a missing currency matters for posting.
            severity = "warning" if f == "currency" else "info"
            issues.append(Issue("MISSING_FIELD", severity, f"{FIELD_LABELS[f]} was not found", f, extra))

    # 2. Numeric sanity ------------------------------------------------------------
    for f in ("subtotal", "tax", "total"):
        v = getattr(inv, f)
        if v is None:
            continue
        if v < 0:
            issues.append(Issue("NEGATIVE_AMOUNT", "warning", f"{FIELD_LABELS[f]} is negative ({v}); credit note?", f))
        if abs(v) >= Decimal("1e12"):
            issues.append(Issue("IMPLAUSIBLE_AMOUNT", "error", f"{FIELD_LABELS[f]} is implausibly large ({v})", f))
    if inv.total is not None and inv.total == 0:
        issues.append(Issue("ZERO_TOTAL", "warning", "Total amount is zero", "total"))
    if inv.subtotal is not None and inv.tax is not None and inv.subtotal > 0:
        rate = inv.tax / inv.subtotal
        if rate > Decimal("0.35"):
            issues.append(Issue("UNUSUAL_TAX_RATE", "warning", f"Tax is {rate:.0%} of subtotal", "tax",
                                {"rate": float(round(rate, 4))}))
    if inv.total is not None and inv.subtotal is not None and inv.total > 0 and inv.subtotal > inv.total and (inv.tax or 0) >= 0:
        issues.append(Issue("SUBTOTAL_EXCEEDS_TOTAL", "error", "Subtotal is larger than the total", "subtotal"))
    for f, raw in inv.rejected.items():
        if f in ("subtotal", "tax", "total") and getattr(inv, f) is None:
            if str(raw).endswith("(range)"):
                shown = str(raw)[: -len(" (range)")]
                issues.append(Issue("AMOUNT_RANGE", "warning",
                                    f"{FIELD_LABELS[f]} is printed as a range ({shown}); enter the agreed amount", f,
                                    {"raw": shown}))
            else:
                issues.append(Issue("INVALID_NUMBER", "error", f"{FIELD_LABELS[f]} value {raw!r} is not a valid amount", f,
                                    {"raw": raw}))
    if inv.document_type not in ("invoice", "", None):
        issues.append(Issue("NOT_AN_INVOICE", "warning",
                            f"This document looks like a {inv.document_type}, not an invoice; invoice-specific fields "
                            "(e.g. invoice number) may legitimately be missing", None, {"document_type": inv.document_type}))

    # 3. Arithmetic consistency ------------------------------------------------------
    if inv.subtotal is not None and inv.tax is not None and inv.total is not None:
        expected = inv.subtotal + inv.tax
        if not _close(expected, inv.total):
            issues.append(Issue(
                "TOTAL_MISMATCH", "error",
                f"Subtotal + tax = {expected} but total is {inv.total} (difference {inv.total - expected})",
                "total", {"expected": str(expected), "actual": str(inv.total), "difference": str(inv.total - expected)},
            ))
    amounts = [li.get("amount") for li in inv.line_items]
    if inv.line_items and all(a is not None for a in amounts):
        line_sum = sum(amounts, Decimal("0"))
        target_field = "subtotal" if inv.subtotal is not None else ("total" if inv.total is not None and not inv.tax else None)
        target = getattr(inv, target_field) if target_field else None
        if target is not None and not _close(line_sum, target):
            issues.append(Issue(
                "LINE_ITEMS_MISMATCH", "error",
                f"Line items sum to {line_sum} but {FIELD_LABELS[target_field].lower()} is {target}",
                target_field, {"line_items_sum": str(line_sum), target_field: str(target), "difference": str(target - line_sum)},
            ))
    elif inv.line_items:
        missing = sum(1 for a in amounts if a is None)
        issues.append(Issue("LINE_ITEM_INCOMPLETE", "warning", f"{missing} line item(s) have no amount", "line_items"))
    for i, li in enumerate(inv.line_items, start=1):
        q, u, a = li.get("quantity"), li.get("unit_price"), li.get("amount")
        if q is not None and u is not None and a is not None and not _close(q * u, a):
            issues.append(Issue(
                "LINE_ITEM_MATH", "warning", f"Line {i}: {q} x {u} = {(q * u).quantize(Decimal('0.01'))}, printed amount is {a}",
                "line_items", {"line": i, "expected": str(q * u), "actual": str(a)},
            ))
    if not inv.line_items:
        issues.append(Issue("NO_LINE_ITEMS", "info", "No line items were found", "line_items"))

    # 4. Dates ---------------------------------------------------------------------
    if inv.invoice_date is not None:
        if inv.invoice_date > today + timedelta(days=1):
            issues.append(Issue("FUTURE_DATE", "warning", f"Invoice date {inv.invoice_date} is in the future", "invoice_date"))
        elif inv.invoice_date < today - timedelta(days=365 * 10):
            issues.append(Issue("OLD_DATE", "warning", f"Invoice date {inv.invoice_date} is more than 10 years old", "invoice_date"))
        if inv.ambiguous_date:
            issues.append(Issue("AMBIGUOUS_DATE", "warning", "Day/month order of the invoice date is ambiguous", "invoice_date"))
    elif "invoice_date" in inv.rejected:
        issues.append(Issue("INVALID_DATE", "error", f"Invoice date {inv.rejected['invoice_date']!r} could not be parsed",
                            "invoice_date"))

    # 5. Currency ------------------------------------------------------------------
    if inv.currency and inv.currency not in CURRENCY_CODES:
        issues.append(Issue("UNKNOWN_CURRENCY", "warning", f"Unrecognised currency {inv.currency!r}", "currency"))

    # 6. Duplicates ----------------------------------------------------------------
    if dup:
        for other in dup.exact:
            issues.append(Issue(
                "DUPLICATE_INVOICE", "error",
                f"Invoice {inv.invoice_number} from this supplier already exists (document {other.get('document_name')})",
                "invoice_number", other,
            ))
        for other in dup.probable:
            issues.append(Issue(
                "POSSIBLE_DUPLICATE", "warning",
                f"Another invoice from this supplier has the same date and total ({other.get('invoice_number')})",
                "invoice_number", other,
            ))

    # 7. Extraction quality ----------------------------------------------------------
    for f, c in inv.confidence.items():
        if f in FIELD_LABELS and getattr(inv, f, None) is not None and c < s.low_field_confidence:
            issues.append(Issue("LOW_CONFIDENCE", "warning", f"{FIELD_LABELS[f]} was extracted with low confidence ({c:.0%})",
                                f, {"confidence": c}))
    for f, raw in inv.rejected.items():
        if f in FIELD_LABELS and getattr(inv, f) is None and f not in ("subtotal", "tax", "total", "invoice_date"):
            issues.append(Issue("UNGROUNDED_VALUE", "warning",
                                f"A proposed {FIELD_LABELS[f].lower()} ({raw!r}) was not found in the document and was discarded",
                                f, {"rejected_value": raw}))
    if inv.min_ocr_confidence is not None and inv.min_ocr_confidence < s.low_ocr_confidence:
        issues.append(Issue("LOW_OCR_QUALITY", "warning",
                            f"OCR confidence is low ({inv.min_ocr_confidence:.0f}/100); verify values against the image",
                            None, {"ocr_confidence": inv.min_ocr_confidence}))
    return issues


def needs_review(issues: list[Issue]) -> bool:
    return any(i.severity in ("error", "warning") for i in issues)


def summarize(issues: list[Issue]) -> tuple[int, int]:
    return sum(i.severity == "error" for i in issues), sum(i.severity == "warning" for i in issues)
