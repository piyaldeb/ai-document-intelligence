"""API request/response models (the public contract; see docs/api.md)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def _decimals_as_numbers(self, v: Any) -> Any:
        if isinstance(v, Decimal):
            return float(v)
        return v


class UploadResult(BaseModel):
    filename: str
    accepted: bool
    document_id: uuid.UUID | None = None
    duplicate_of: uuid.UUID | None = None
    error: str | None = None


class UploadResponse(BaseModel):
    accepted: int
    rejected: int
    results: list[UploadResult]


class DocumentSummary(_Out):
    id: uuid.UUID
    original_filename: str
    file_type: str
    size_bytes: int
    status: str
    stage: str | None
    progress: int
    page_count: int | None
    invoice_count: int
    error_code: str | None
    error_message: str | None
    attempts: int
    duplicate_of_id: uuid.UUID | None
    extraction_provider: str | None
    created_at: datetime
    processing_started_at: datetime | None
    processing_finished_at: datetime | None
    processing_ms: int | None


class DocumentStatusOut(_Out):
    id: uuid.UUID
    status: str
    stage: str | None
    progress: int
    error_code: str | None
    error_message: str | None
    invoice_count: int
    processing_ms: int | None


class PageMeta(_Out):
    page_number: int
    sheet_name: str | None
    method: str
    ocr_confidence: float | None
    char_count: int
    warnings: list[str]


class PageOut(PageMeta):
    text: str


class EventOut(_Out):
    id: int
    attempt: int
    stage: str
    status: str
    message: str | None
    duration_ms: int | None
    created_at: datetime


class IssueOut(_Out):
    id: int
    invoice_id: uuid.UUID | None
    code: str
    severity: str
    field: str | None
    message: str
    details: dict[str, Any]


class LineItemOut(_Out):
    id: int
    position: int
    description: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None


class CorrectionOut(_Out):
    id: int
    field: str
    old_value: Any
    new_value: Any
    reason: str | None
    corrected_by: str | None
    created_at: datetime


class InvoiceSummary(_Out):
    id: uuid.UUID
    document_id: uuid.UUID
    sequence: int
    invoice_number: str | None
    invoice_date: date | None
    supplier_name: str | None
    customer_name: str | None
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal | None
    currency: str | None
    review_status: str
    needs_review: bool
    error_count: int
    warning_count: int
    extraction_method: str
    page_start: int | None
    page_end: int | None
    source_ref: dict[str, Any]


class InvoiceDetail(InvoiceSummary):
    document_name: str | None = None
    field_confidence: dict[str, float]
    model: str | None
    raw_extraction: dict[str, Any]
    source_text: str
    line_items: list[LineItemOut]
    issues: list[IssueOut]
    corrections: list[CorrectionOut]
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentSummary):
    sha256: str
    mime_type: str
    meta: dict[str, Any]
    pages: list[PageMeta]
    invoices: list[InvoiceSummary]
    events: list[EventOut]
    issues: list[IssueOut]


class Page(BaseModel):
    total: int
    page: int
    page_size: int


class DocumentList(BaseModel):
    items: list[DocumentSummary]
    meta: Page


class InvoiceList(BaseModel):
    items: list[InvoiceSummary]
    meta: Page


class LineItemIn(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class InvoiceCorrection(BaseModel):
    """Only the fields present in the request body are changed (null clears a value)."""

    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None = Field(default=None, max_length=64)
    invoice_date: date | None = None
    supplier_name: str | None = Field(default=None, max_length=300)
    customer_name: str | None = Field(default=None, max_length=300)
    subtotal: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    tax: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    total: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    line_items: list[LineItemIn] | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=500)
    corrected_by: str | None = Field(default=None, max_length=128)


class ApproveRequest(BaseModel):
    approved_by: str | None = Field(default=None, max_length=128)
    force: bool = False


class SearchHitOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    invoice_id: uuid.UUID | None
    page_number: int | None
    snippet: str
    score: float
    match: str
    sources: list[str]
    invoice: dict[str, Any] | None


class SearchResponse(BaseModel):
    query: str
    mode: Literal["keyword", "semantic", "hybrid"]
    took_ms: int
    results: list[SearchHitOut]


class ReprocessResponse(BaseModel):
    queued: list[uuid.UUID]


class ReconcileRequest(BaseModel):
    left_document_id: uuid.UUID
    right_document_id: uuid.UUID
    amount_tolerance: Decimal = Field(default=Decimal("0.01"), ge=0, le=1000)


class ReconciliationItemOut(_Out):
    id: int
    match_key: str | None
    status: str
    left_invoice_id: uuid.UUID | None
    right_invoice_id: uuid.UUID | None
    differences: list[dict[str, Any]]
    left: InvoiceSummary | None = None
    right: InvoiceSummary | None = None


class ReconciliationOut(_Out):
    id: uuid.UUID
    left_document_id: uuid.UUID
    right_document_id: uuid.UUID
    left_document_name: str | None = None
    right_document_name: str | None = None
    summary: dict[str, Any]
    params: dict[str, Any]
    created_at: datetime
    items: list[ReconciliationItemOut] = []


class Stats(BaseModel):
    documents: dict[str, int]
    invoices: dict[str, int]
    issues_by_code: dict[str, int]
    avg_processing_ms: float | None
    total_amount_by_currency: dict[str, float]
    extraction_provider: str
