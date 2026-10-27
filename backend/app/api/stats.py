from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Document, Invoice, ValidationIssue
from app.schemas import Stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=Stats)
def stats(db: Session = Depends(get_db)) -> Stats:
    docs = dict(db.execute(select(Document.status, func.count()).group_by(Document.status)).all())
    invs = dict(db.execute(select(Invoice.review_status, func.count()).group_by(Invoice.review_status)).all())
    issues = dict(db.execute(
        select(ValidationIssue.code, func.count()).where(ValidationIssue.severity != "info")
        .group_by(ValidationIssue.code).order_by(func.count().desc()).limit(15)
    ).all())
    avg_ms = db.scalar(select(func.avg(Document.processing_ms)).where(Document.processing_ms.is_not(None)))
    totals = {
        (cur or "unknown"): float(amount or 0)
        for cur, amount in db.execute(select(Invoice.currency, func.sum(Invoice.total)).group_by(Invoice.currency)).all()
    }
    docs["total"] = sum(docs.values())
    invs["total"] = sum(invs.values())
    return Stats(documents=docs, invoices=invs, issues_by_code=issues,
                 avg_processing_ms=float(avg_ms) if avg_ms is not None else None,
                 total_amount_by_currency=totals, extraction_provider=get_settings().effective_provider)
