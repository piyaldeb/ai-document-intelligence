"""Persisting extracted invoices and (re)running validation against the database."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, delete, false, func, or_, select, text, true
from sqlalchemy.orm import Session

from app.extraction.normalize import money, normalize_company, normalize_invoice_number
from app.extraction.schema import InvoiceData
from app.models import Document, Invoice, LineItem, ReviewStatus, ValidationIssue
from app.validation.rules import DuplicateContext, InvoiceView, Issue, needs_review, summarize, validate


def lock_invoice_key(db: Session, number_norm: str | None) -> None:
    """Serialise concurrent workers inserting the same invoice number (duplicate detection race)."""
    if number_norm:
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"invoice:{number_norm}"})


def find_duplicates(db: Session, inv: Invoice) -> DuplicateContext:
    ctx = DuplicateContext()
    if inv.invoice_number_norm:
        conds = [Invoice.invoice_number_norm == inv.invoice_number_norm, Invoice.id != inv.id]
        # Same number + same supplier, or same number + same total when a supplier is unknown.
        supplier_unknown = true() if inv.supplier_norm is None else Invoice.supplier_norm.is_(None)
        same_total = (Invoice.total == inv.total) if inv.total is not None else false()
        loose = and_(supplier_unknown, same_total)
        cond = or_(Invoice.supplier_norm == inv.supplier_norm, loose) if inv.supplier_norm else loose
        rows = db.execute(
            select(Invoice.id, Invoice.document_id, Invoice.invoice_number, Document.original_filename)
            .join(Document, Document.id == Invoice.document_id)
            .where(*conds, cond)
            .order_by(Invoice.created_at)
            .limit(5)
        ).all()
        ctx.exact = [
            {"invoice_id": str(r.id), "document_id": str(r.document_id), "invoice_number": r.invoice_number,
             "document_name": r.original_filename}
            for r in rows
        ]
    if inv.supplier_norm and inv.invoice_date and inv.total is not None:
        rows = db.execute(
            select(Invoice.id, Invoice.document_id, Invoice.invoice_number, Document.original_filename)
            .join(Document, Document.id == Invoice.document_id)
            .where(
                Invoice.id != inv.id,
                Invoice.supplier_norm == inv.supplier_norm,
                Invoice.invoice_date == inv.invoice_date,
                Invoice.total == inv.total,
                or_(Invoice.invoice_number_norm.is_(None), Invoice.invoice_number_norm != (inv.invoice_number_norm or "")),
            )
            .limit(5)
        ).all()
        ctx.probable = [
            {"invoice_id": str(r.id), "document_id": str(r.document_id), "invoice_number": r.invoice_number,
             "document_name": r.original_filename}
            for r in rows
        ]
    return ctx


def view_of(inv: Invoice) -> InvoiceView:
    raw = inv.raw_extraction or {}
    return InvoiceView(
        invoice_number=inv.invoice_number,
        invoice_date=inv.invoice_date,
        supplier_name=inv.supplier_name,
        customer_name=inv.customer_name,
        subtotal=inv.subtotal,
        tax=inv.tax,
        total=inv.total,
        currency=inv.currency,
        line_items=[{"quantity": li.quantity, "unit_price": li.unit_price, "amount": li.amount} for li in inv.line_items],
        confidence=dict(inv.field_confidence or {}),
        rejected=dict(raw.get("rejected") or {}),
        ambiguous_date=bool(raw.get("ambiguous_date")) and not raw.get("date_corrected"),
        min_ocr_confidence=raw.get("min_ocr_confidence"),
    )


def apply_validation(db: Session, inv: Invoice) -> list[Issue]:
    db.execute(delete(ValidationIssue).where(ValidationIssue.invoice_id == inv.id))
    issues = validate(view_of(inv), find_duplicates(db, inv))
    for it in issues:
        db.add(ValidationIssue(
            document_id=inv.document_id, invoice_id=inv.id, code=it.code, severity=it.severity,
            field=it.field, message=it.message, details=it.details,
        ))
    errors, warnings = summarize(issues)
    inv.error_count, inv.warning_count = errors, warnings
    inv.needs_review = needs_review(issues)
    if inv.review_status != ReviewStatus.APPROVED or errors:
        inv.review_status = ReviewStatus.NEEDS_REVIEW if inv.needs_review else ReviewStatus.OK
    return issues


def _dec(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def create_invoice(
    db: Session,
    document: Document,
    data: InvoiceData,
    *,
    sequence: int,
    source_ref: dict[str, Any],
    source_text: str,
    min_ocr_confidence: float | None,
) -> Invoice:
    number_norm = normalize_invoice_number(data.invoice_number)
    lock_invoice_key(db, number_norm)
    raw = data.model_dump(mode="json", exclude={"line_items"})
    raw["min_ocr_confidence"] = min_ocr_confidence
    inv = Invoice(
        id=uuid.uuid4(),
        document_id=document.id,
        sequence=sequence,
        source_ref=source_ref,
        page_start=source_ref.get("pages", [None])[0] if source_ref.get("pages") else None,
        page_end=source_ref.get("pages", [None])[-1] if source_ref.get("pages") else None,
        invoice_number=data.invoice_number,
        invoice_number_norm=number_norm,
        invoice_date=data.invoice_date,
        supplier_name=data.supplier_name,
        supplier_norm=normalize_company(data.supplier_name),
        customer_name=data.customer_name,
        subtotal=money(data.subtotal),
        tax=money(data.tax),
        total=money(data.total),
        currency=data.currency,
        field_confidence=data.confidence,
        extraction_method=data.method,
        model=data.model,
        raw_extraction=raw,
        source_text=source_text[:20000],
    )
    inv.line_items = [
        LineItem(position=i, description=li.description, quantity=_dec(li.quantity),
                 unit_price=_dec(li.unit_price), amount=money(li.amount))
        for i, li in enumerate(data.line_items, start=1)
    ]
    db.add(inv)
    db.flush()
    apply_validation(db, inv)
    return inv


def refresh_document_rollup(db: Session, document: Document) -> None:
    from app.models import DocumentStatus

    counts = db.execute(
        select(func.count(Invoice.id), func.count(Invoice.id).filter(Invoice.needs_review.is_(True)))
        .where(Invoice.document_id == document.id)
    ).one()
    document.invoice_count = counts[0]
    if document.status in (DocumentStatus.COMPLETED, DocumentStatus.NEEDS_REVIEW):
        doc_level = db.scalar(
            select(func.count(ValidationIssue.id)).where(
                ValidationIssue.document_id == document.id,
                ValidationIssue.invoice_id.is_(None),
                ValidationIssue.severity.in_(("error", "warning")),
            )
        )
        document.status = DocumentStatus.NEEDS_REVIEW if (counts[1] or doc_level) else DocumentStatus.COMPLETED
