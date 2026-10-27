from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Document, DocumentStatus, Invoice, Reconciliation
from app.schemas import InvoiceSummary, ReconcileRequest, ReconciliationItemOut, ReconciliationOut
from app.services.reconcile import reconcile

router = APIRouter(prefix="/api/reconciliations", tags=["cross-verification"])


def _out(db: Session, rec: Reconciliation, with_items: bool = True) -> ReconciliationOut:
    names = dict(db.execute(select(Document.id, Document.original_filename).where(
        Document.id.in_([rec.left_document_id, rec.right_document_id]))).all())
    out = ReconciliationOut(
        id=rec.id, left_document_id=rec.left_document_id, right_document_id=rec.right_document_id,
        left_document_name=names.get(rec.left_document_id), right_document_name=names.get(rec.right_document_id),
        summary=rec.summary, params=rec.params, created_at=rec.created_at, items=[],
    )
    if with_items:
        ids = {i for it in rec.items for i in (it.left_invoice_id, it.right_invoice_id) if i}
        invoices = {inv.id: inv for inv in db.scalars(select(Invoice).where(Invoice.id.in_(ids)))} if ids else {}
        for it in rec.items:
            item = ReconciliationItemOut.model_validate(it)
            if it.left_invoice_id in invoices:
                item.left = InvoiceSummary.model_validate(invoices[it.left_invoice_id])
            if it.right_invoice_id in invoices:
                item.right = InvoiceSummary.model_validate(invoices[it.right_invoice_id])
            out.items.append(item)
    return out


@router.post("", response_model=ReconciliationOut, status_code=status.HTTP_201_CREATED)
def create_reconciliation(body: ReconcileRequest, db: Session = Depends(get_db)) -> ReconciliationOut:
    """Cross-verify two processed documents (e.g. supplier PDF vs. ERP Excel export)."""
    if body.left_document_id == body.right_document_id:
        raise HTTPException(422, "Choose two different documents")
    for doc_id in (body.left_document_id, body.right_document_id):
        doc = db.get(Document, doc_id)
        if doc is None:
            raise HTTPException(404, f"Document {doc_id} not found")
        if doc.status not in (DocumentStatus.COMPLETED, DocumentStatus.NEEDS_REVIEW):
            raise HTTPException(409, f"Document {doc.original_filename} is not processed yet ({doc.status})")
    rec = reconcile(db, body.left_document_id, body.right_document_id, body.amount_tolerance)
    db.commit()
    return _out(db, rec)


@router.get("", response_model=list[ReconciliationOut])
def list_reconciliations(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)) -> list[ReconciliationOut]:
    recs = db.scalars(select(Reconciliation).order_by(Reconciliation.created_at.desc()).limit(limit)).all()
    return [_out(db, r, with_items=False) for r in recs]


@router.get("/{reconciliation_id}", response_model=ReconciliationOut)
def get_reconciliation(reconciliation_id: uuid.UUID, db: Session = Depends(get_db)) -> ReconciliationOut:
    rec = db.scalar(select(Reconciliation).where(Reconciliation.id == reconciliation_id)
                    .options(selectinload(Reconciliation.items)))
    if rec is None:
        raise HTTPException(404, "Reconciliation not found")
    return _out(db, rec)
