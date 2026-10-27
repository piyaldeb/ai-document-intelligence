"""Claude-based extraction with schema-constrained (structured) output."""

from __future__ import annotations

import logging
import threading
from datetime import date
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from app.config import get_settings
from app.extraction.normalize import money, normalize_currency, parse_amount
from app.extraction.prompts import SYSTEM_PROMPT, USER_TEMPLATE
from app.extraction.schema import InvoiceData, LineItemData

log = logging.getLogger(__name__)

CONFIDENCE = {"high": 0.95, "medium": 0.8, "low": 0.5}


class LLMError(Exception):
    pass


class ExtractedField(BaseModel):
    value: str | None = Field(description="The value, or null if not printed in the document")
    confidence: Literal["high", "medium", "low"]
    evidence: str | None = Field(description="Exact snippet of document text supporting the value")


class ExtractedLineItem(BaseModel):
    description: str | None
    quantity: str | None
    unit_price: str | None
    amount: str | None


class ExtractedInvoice(BaseModel):
    is_invoice: bool = Field(description="False if the document is not an invoice, bill or receipt")
    invoice_number: ExtractedField
    invoice_date: ExtractedField
    supplier_name: ExtractedField
    customer_name: ExtractedField
    subtotal: ExtractedField
    tax: ExtractedField
    total: ExtractedField
    currency: ExtractedField
    line_items: list[ExtractedLineItem]
    notes: str | None


_client: anthropic.Anthropic | None = None
_client_lock = threading.Lock()
_fallbacks_supported = True


def _get_client() -> anthropic.Anthropic:
    global _client
    with _client_lock:
        if _client is None:
            s = get_settings()
            if not s.anthropic_api_key:
                raise LLMError("ANTHROPIC_API_KEY is not configured")
            _client = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.llm_timeout_s, max_retries=3)
        return _client


def _call(text: str, context: str) -> tuple[ExtractedInvoice, str]:
    global _fallbacks_supported
    s = get_settings()
    client = _get_client()
    kwargs = dict(
        model=s.llm_model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": USER_TEMPLATE.format(text=text, context=context)}],
        output_format=ExtractedInvoice,
        output_config={"effort": s.llm_effort},
    )
    if s.llm_server_fallbacks and _fallbacks_supported:
        try:
            # On a policy decline the API re-runs the request on a fallback model server-side.
            response = client.beta.messages.parse(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        except TypeError:
            _fallbacks_supported = False
            log.warning("installed anthropic SDK does not support `fallbacks`; continuing without")
            response = client.messages.parse(**kwargs)
    else:
        response = client.messages.parse(**kwargs)

    if response.stop_reason == "refusal":
        raise LLMError("model declined the request")
    if response.stop_reason == "max_tokens":
        raise LLMError("model output was truncated (max_tokens)")
    parsed = response.parsed_output
    if parsed is None:
        raise LLMError("model returned no structured output")
    return parsed, response.model


def extract(text: str, *, context: str = "", dayfirst: bool = True) -> InvoiceData:
    s = get_settings()
    notes: list[str] = []
    if len(text) > s.llm_max_input_chars:
        notes.append(
            f"document text ({len(text)} chars) exceeded the LLM input limit; only the first "
            f"{s.llm_max_input_chars} chars were sent"
        )
        text = text[: s.llm_max_input_chars]
    try:
        out, model = _call(text, context)
    except anthropic.AuthenticationError as exc:
        raise LLMError(f"authentication failed: {exc.message}") from exc
    except anthropic.BadRequestError as exc:
        raise LLMError(f"bad request: {exc.message}") from exc
    except anthropic.RateLimitError as exc:
        raise LLMError("rate limited after retries") from exc
    except anthropic.APIStatusError as exc:
        raise LLMError(f"API error {exc.status_code}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMError(f"connection error: {exc}") from exc
    return to_invoice_data(out, model, dayfirst, notes)


def to_invoice_data(out: ExtractedInvoice, model: str | None, dayfirst: bool, notes: list[str]) -> InvoiceData:
    data = InvoiceData(method="anthropic", model=model, notes=list(notes))
    if not out.is_invoice:
        data.document_type = "other"
        data.notes.append("model reports the document is not an invoice")

    def conf(f: ExtractedField) -> float:
        return CONFIDENCE.get(f.confidence, 0.5)

    for name in ("invoice_number", "supplier_name", "customer_name"):
        f: ExtractedField = getattr(out, name)
        if f.value and f.value.strip():
            data.set(name, f.value.strip(), conf(f), f.evidence)
    if out.invoice_date.value:
        try:
            data.set("invoice_date", date.fromisoformat(out.invoice_date.value.strip()), conf(out.invoice_date),
                     out.invoice_date.evidence)
        except ValueError:
            data.rejected["invoice_date"] = out.invoice_date.value
            data.notes.append(f"model returned a non-ISO date {out.invoice_date.value!r}")
    for name in ("subtotal", "tax", "total"):
        f = getattr(out, name)
        if f.value:
            amount = parse_amount(f.value)
            if amount is None:
                data.rejected[name] = f.value
                data.notes.append(f"model returned a non-numeric {name} {f.value!r}")
            else:
                data.set(name, money(amount), conf(f), f.evidence)
    if out.currency.value:
        code = normalize_currency(out.currency.value)
        if code:
            data.set("currency", code, conf(out.currency), out.currency.evidence)
        else:
            data.rejected["currency"] = out.currency.value
    for li in out.line_items:
        data.line_items.append(
            LineItemData(
                description=(li.description or "").strip() or None,
                quantity=parse_amount(li.quantity),
                unit_price=parse_amount(li.unit_price),
                amount=money(parse_amount(li.amount)),
            )
        )
    if data.line_items:
        data.confidence["line_items"] = 0.9
    if out.notes:
        data.notes.append(out.notes)
    return data
