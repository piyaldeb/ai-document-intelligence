"""Extraction orchestration: provider selection, LLM + rules cross-check, grounding."""

from __future__ import annotations

import logging

from app.config import get_settings
from app.extraction import rules
from app.extraction.grounding import ground
from app.extraction.normalize import normalize_company, normalize_invoice_number
from app.extraction.schema import SCALAR_FIELDS, InvoiceData

log = logging.getLogger(__name__)


def _same(field: str, a, b) -> bool:
    if a is None or b is None:
        return False
    if field == "invoice_number":
        return normalize_invoice_number(a) == normalize_invoice_number(b)
    if field in ("supplier_name", "customer_name"):
        return normalize_company(a) == normalize_company(b)
    return a == b


def _merge(primary: InvoiceData, check: InvoiceData) -> InvoiceData:
    """Calibrate LLM confidence against the independent rules extractor."""
    agreement = {}
    for field in SCALAR_FIELDS:
        a, b = getattr(primary, field), getattr(check, field)
        if a is None:
            continue
        base = primary.confidence.get(field, 0.8)
        if _same(field, a, b):
            primary.confidence[field] = round(min(0.99, base + 0.04), 3)
            agreement[field] = "agree"
        elif b is not None:
            primary.confidence[field] = round(base * 0.85, 3)
            agreement[field] = f"rules extractor found {b}"
    if agreement:
        primary.evidence.setdefault("_cross_check", "; ".join(f"{k}: {v}" for k, v in agreement.items()))
    return primary


def extract_text(text: str, provider: str | None = None, context: str = "") -> InvoiceData:
    """Extract one invoice from (layout) text."""
    provider = provider or get_settings().effective_provider
    rules_result = rules.extract(text)
    if provider != "anthropic":
        return rules_result
    from app.extraction import llm  # the Anthropic SDK is only loaded when Claude is enabled

    dayfirst = rules_result.currency != "USD"
    try:
        result = llm.extract(text, context=context, dayfirst=dayfirst)
    except llm.LLMError as exc:
        log.warning("LLM extraction failed, using rules extractor: %s", exc)
        rules_result.notes.append(f"LLM extraction unavailable ({exc}); used rules extractor")
        return rules_result
    result = ground(result, text)
    if result.document_type == "other" and rules_result.document_type != "invoice":
        result.document_type = rules_result.document_type  # more specific: quotation, purchase order, ...
    return _merge(result, rules_result)
