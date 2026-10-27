"""Scoring helpers shared by run_eval.py and offline_check.py."""

from __future__ import annotations

from decimal import Decimal

from rapidfuzz import fuzz

from app.extraction.normalize import normalize_company, normalize_invoice_number

FIELDS = ["invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency"]


def same(field: str, pred, gt) -> bool:
    if pred is None or gt is None:
        return pred is None and gt is None
    if field == "invoice_number":
        return normalize_invoice_number(str(pred)) == normalize_invoice_number(str(gt))
    if field in ("subtotal", "tax", "total"):
        return abs(Decimal(str(pred)) - Decimal(str(gt))) <= Decimal("0.01")
    if field in ("supplier_name", "customer_name"):
        a, b = normalize_company(str(pred)) or "", normalize_company(str(gt)) or ""
        return a == b or fuzz.token_sort_ratio(a, b) >= 92
    return str(pred) == str(gt)


def match_invoices(preds: list[dict], gts: list[dict]) -> list[tuple[dict | None, dict]]:
    """Pair each ground-truth invoice with at most one prediction (by number, then total, then order)."""
    remaining = list(preds)
    pairs: list[tuple[dict | None, dict]] = []
    unmatched_gt = []
    for gt in gts:
        key = normalize_invoice_number(gt["invoice_number"])
        hit = next((p for p in remaining if key and normalize_invoice_number(p.get("invoice_number")) == key), None)
        if hit:
            remaining.remove(hit)
            pairs.append((hit, gt))
        else:
            unmatched_gt.append(gt)
    for gt in unmatched_gt:
        hit = next((p for p in remaining if p.get("total") is not None and same("total", p["total"], gt["total"])), None)
        if hit is None and remaining and len(gts) == 1:
            hit = remaining[0]
        if hit:
            remaining.remove(hit)
        pairs.append((hit, gt))
    return pairs
