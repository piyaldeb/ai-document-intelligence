"""Cross-verification of two processed documents (PDF vs PDF, PDF vs Excel/CSV, ...).

Invoices are matched by normalised invoice number; unmatched ones fall back to
(supplier, date, total). Matched pairs are compared field by field.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.extraction.normalize import normalize_company
from app.models import Invoice, Reconciliation, ReconciliationItem

COMPARED = ("invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency")


def _fmt(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return str(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _equal(field: str, a: Any, b: Any, tolerance: Decimal) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if field in ("subtotal", "tax", "total"):
        return abs(Decimal(a) - Decimal(b)) <= tolerance
    if field in ("supplier_name", "customer_name"):
        na, nb = normalize_company(a) or "", normalize_company(b) or ""
        return na == nb or fuzz.token_sort_ratio(na, nb) >= 90
    return a == b


def compare(left: Invoice, right: Invoice, tolerance: Decimal) -> list[dict[str, Any]]:
    diffs = []
    for f in COMPARED:
        a, b = getattr(left, f), getattr(right, f)
        if not _equal(f, a, b, tolerance):
            diffs.append({"field": f, "left": _fmt(a), "right": _fmt(b)})
    if left.line_items and right.line_items and len(left.line_items) != len(right.line_items):
        diffs.append({"field": "line_items_count", "left": len(left.line_items), "right": len(right.line_items)})
    return diffs


def _fallback_key(inv: Invoice) -> tuple | None:
    if inv.invoice_date and inv.total is not None:
        return (normalize_company(inv.supplier_name), inv.invoice_date, inv.total)
    return None


def reconcile(db: Session, left_id: uuid.UUID, right_id: uuid.UUID, tolerance: Decimal = Decimal("0.01")) -> Reconciliation:
    def load(doc_id: uuid.UUID) -> list[Invoice]:
        return list(db.scalars(
            select(Invoice).where(Invoice.document_id == doc_id).options(selectinload(Invoice.line_items))
            .order_by(Invoice.sequence)
        ))

    left, right = load(left_id), load(right_id)
    rec = Reconciliation(left_document_id=left_id, right_document_id=right_id,
                         params={"tolerance": str(tolerance)})
    right_by_no: dict[str, list[Invoice]] = {}
    for inv in right:
        if inv.invoice_number_norm:
            right_by_no.setdefault(inv.invoice_number_norm, []).append(inv)
    used: set[uuid.UUID] = set()
    items: list[ReconciliationItem] = []
    unmatched_left: list[Invoice] = []
    for inv in left:
        candidates = [c for c in right_by_no.get(inv.invoice_number_norm or "", []) if c.id not in used]
        if not candidates:
            unmatched_left.append(inv)
            continue
        other = candidates[0]
        used.add(other.id)
        diffs = compare(inv, other, tolerance)
        items.append(ReconciliationItem(
            match_key=inv.invoice_number, status="mismatch" if diffs else "matched",
            left_invoice_id=inv.id, right_invoice_id=other.id, differences=diffs,
        ))
    # Second pass: no shared invoice number, but same supplier/date/total.
    right_by_fallback: dict[tuple, list[Invoice]] = {}
    for inv in right:
        if inv.id not in used and (k := _fallback_key(inv)):
            right_by_fallback.setdefault(k, []).append(inv)
    for inv in unmatched_left:
        k = _fallback_key(inv)
        candidates = [c for c in right_by_fallback.get(k, []) if c.id not in used] if k else []
        if candidates:
            other = candidates[0]
            used.add(other.id)
            diffs = compare(inv, other, tolerance)
            diffs.insert(0, {"field": "invoice_number", "left": inv.invoice_number, "right": other.invoice_number})
            items.append(ReconciliationItem(match_key=inv.invoice_number or other.invoice_number, status="mismatch",
                                            left_invoice_id=inv.id, right_invoice_id=other.id, differences=diffs))
        else:
            items.append(ReconciliationItem(match_key=inv.invoice_number, status="missing_in_right",
                                            left_invoice_id=inv.id, differences=[]))
    for inv in right:
        if inv.id not in used:
            items.append(ReconciliationItem(match_key=inv.invoice_number, status="missing_in_left",
                                            right_invoice_id=inv.id, differences=[]))
    rec.items = items
    summary: dict[str, Any] = {"left_invoices": len(left), "right_invoices": len(right)}
    for status in ("matched", "mismatch", "missing_in_left", "missing_in_right"):
        summary[status] = sum(1 for i in items if i.status == status)
    field_counts: dict[str, int] = {}
    for i in items:
        for d in i.differences:
            field_counts[d["field"]] = field_counts.get(d["field"], 0) + 1
    summary["mismatched_fields"] = field_counts
    rec.summary = summary
    db.add(rec)
    db.flush()
    return rec
