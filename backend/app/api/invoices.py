from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.extraction.normalize import money, normalize_company, normalize_invoice_number
from app.models import Correction, Document, Invoice, LineItem, ReviewStatus
from app.schemas import (
    ApproveRequest,
    InvoiceCorrection,
    InvoiceDetail,
    InvoiceList,
    InvoiceSummary,
    Page,
)
from app.search.service import SearchFilters, invoice_list_query
from app.services.invoices import apply_validation, lock_invoice_key, refresh_document_rollup

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

SORTS = {
    "created_desc": Invoice.created_at.desc(),
    "date_desc": Invoice.invoice_date.desc().nullslast(),
    "date_asc": Invoice.invoice_date.asc().nullslast(),
    "total_desc": Invoice.total.desc().nullslast(),
    "total_asc": Invoice.total.asc().nullslast(),
    "issues_desc": (Invoice.error_count * 100 + Invoice.warning_count).desc(),
}


@router.get("", response_model=InvoiceList)
def list_invoices(
    q: str | None = Query(None, max_length=200, description="keyword across number / supplier / customer"),
    supplier: str | None = Query(None, max_length=200),
    customer: str | None = Query(None, max_length=200),
    invoice_number: str | None = Query(None, max_length=64),
    currency: str | None = Query(None, max_length=3),
    date_from: date | None = None,
    date_to: date | None = None,
    min_total: Decimal | None = None,
    max_total: Decimal | None = None,
    review_status: str | None = Query(None, pattern="^(ok|needs_review|approved)$"),
    issue_code: str | None = Query(None, max_length=64),
    file_type: str | None = None,
    document_id: uuid.UUID | None = None,
    sort: str = Query("created_desc", pattern="^(" + "|".join(SORTS) + ")$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
) -> InvoiceList:
    """Keyword-based filtering over extracted invoices."""
    f = SearchFilters(supplier=supplier, customer=customer, invoice_number=invoice_number, currency=currency,
                      date_from=date_from, date_to=date_to, min_total=min_total, max_total=max_total,
                      review_status=review_status, file_type=file_type, document_id=document_id)
    stmt = invoice_list_query(f, q)
    if issue_code:
        from app.models import ValidationIssue

        stmt = stmt.where(Invoice.id.in_(select(ValidationIssue.invoice_id).where(ValidationIssue.code == issue_code)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(SORTS[sort], Invoice.id).offset((page - 1) * page_size).limit(page_size)).all()
    return InvoiceList(items=[InvoiceSummary.model_validate(r) for r in rows],
                       meta=Page(total=total, page=page, page_size=page_size))


def _load(db: Session, invoice_id: uuid.UUID) -> Invoice:
    inv = db.scalar(
        select(Invoice).where(Invoice.id == invoice_id).options(
            selectinload(Invoice.line_items), selectinload(Invoice.issues), selectinload(Invoice.corrections),
        )
    )
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return inv


def _detail(db: Session, inv: Invoice) -> InvoiceDetail:
    out = InvoiceDetail.model_validate(inv)
    out.document_name = db.scalar(select(Document.original_filename).where(Document.id == inv.document_id))
    return out


@router.get("/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(invoice_id: uuid.UUID, db: Session = Depends(get_db)) -> InvoiceDetail:
    return _detail(db, _load(db, invoice_id))


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


@router.patch("/{invoice_id}", response_model=InvoiceDetail)
def correct_invoice(invoice_id: uuid.UUID, body: InvoiceCorrection, db: Session = Depends(get_db)) -> InvoiceDetail:
    """Manual correction. Every changed field is written to the audit trail and the
    invoice is re-validated (including duplicate checks)."""
    inv = _load(db, invoice_id)
    changes = body.model_dump(exclude_unset=True, exclude={"reason", "corrected_by", "line_items"})
    if not changes and body.line_items is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No fields to change")
    raw = dict(inv.raw_extraction or {})
    rejected = dict(raw.get("rejected") or {})
    confidence = dict(inv.field_confidence or {})
    for field, new in changes.items():
        if field in ("subtotal", "tax", "total"):
            new = money(new)
        if field == "currency" and new:
            new = new.upper()
        if isinstance(new, str):
            new = new.strip() or None
        old = getattr(inv, field)
        if old == new:
            continue
        db.add(Correction(invoice_id=inv.id, field=field, old_value=_jsonable(old), new_value=_jsonable(new),
                          reason=body.reason, corrected_by=body.corrected_by))
        setattr(inv, field, new)
        confidence[field] = 1.0  # human-verified
        rejected.pop(field, None)
        if field == "invoice_date":
            raw["date_corrected"] = True
    if body.line_items is not None:
        old_items = [{"description": li.description, "quantity": _jsonable(li.quantity),
                      "unit_price": _jsonable(li.unit_price), "amount": _jsonable(li.amount)} for li in inv.line_items]
        new_items = [li.model_dump(mode="json") for li in body.line_items]
        db.add(Correction(invoice_id=inv.id, field="line_items", old_value=old_items, new_value=new_items,
                          reason=body.reason, corrected_by=body.corrected_by))
        inv.line_items = [
            LineItem(position=i, description=li.description, quantity=li.quantity, unit_price=li.unit_price,
                     amount=money(li.amount))
            for i, li in enumerate(body.line_items, start=1)
        ]
        confidence["line_items"] = 1.0
    raw["rejected"] = rejected
    inv.raw_extraction = raw
    inv.field_confidence = confidence
    inv.invoice_number_norm = normalize_invoice_number(inv.invoice_number)
    inv.supplier_norm = normalize_company(inv.supplier_name)
    if inv.review_status == ReviewStatus.APPROVED:
        inv.review_status = ReviewStatus.NEEDS_REVIEW  # changed after approval: approve again
    lock_invoice_key(db, inv.invoice_number_norm)
    db.flush()
    apply_validation(db, inv)
    refresh_document_rollup(db, db.get(Document, inv.document_id))
    db.commit()
    db.expire_all()
    return _detail(db, _load(db, invoice_id))


@router.post("/{invoice_id}/approve", response_model=InvoiceDetail)
def approve_invoice(invoice_id: uuid.UUID, body: ApproveRequest | None = None, db: Session = Depends(get_db)) -> InvoiceDetail:
    body = body or ApproveRequest()
    inv = _load(db, invoice_id)
    if inv.error_count and not body.force:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Invoice still has {inv.error_count} validation error(s); correct them or pass force=true")
    db.add(Correction(invoice_id=inv.id, field="review_status", old_value=inv.review_status, new_value="approved",
                      reason="forced approval" if inv.error_count else "approved", corrected_by=body.approved_by))
    inv.review_status = ReviewStatus.APPROVED
    inv.needs_review = False
    db.flush()
    refresh_document_rollup(db, db.get(Document, inv.document_id))
    db.commit()
    db.expire_all()
    return _detail(db, _load(db, invoice_id))
