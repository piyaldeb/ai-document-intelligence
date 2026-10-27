"""Keyword (PostgreSQL full-text + trigram), semantic (pgvector) and hybrid (RRF) search."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import Chunk, Document, DocumentPage, Invoice


@dataclass
class SearchFilters:
    supplier: str | None = None
    customer: str | None = None
    invoice_number: str | None = None
    currency: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_total: Decimal | None = None
    max_total: Decimal | None = None
    review_status: str | None = None
    file_type: str | None = None
    document_id: uuid.UUID | None = None


@dataclass
class Hit:
    key: str
    document_id: uuid.UUID
    document_name: str
    invoice_id: uuid.UUID | None
    page_number: int | None
    snippet: str
    score: float
    match: str  # keyword | semantic | hybrid
    invoice: dict[str, Any] | None = None
    sources: list[str] = field(default_factory=list)


def apply_invoice_filters(stmt: Select, f: SearchFilters) -> Select:
    if f.supplier:
        stmt = stmt.where(Invoice.supplier_name.ilike(f"%{f.supplier}%"))
    if f.customer:
        stmt = stmt.where(Invoice.customer_name.ilike(f"%{f.customer}%"))
    if f.invoice_number:
        stmt = stmt.where(Invoice.invoice_number.ilike(f"%{f.invoice_number}%"))
    if f.currency:
        stmt = stmt.where(Invoice.currency == f.currency.upper())
    if f.date_from:
        stmt = stmt.where(Invoice.invoice_date >= f.date_from)
    if f.date_to:
        stmt = stmt.where(Invoice.invoice_date <= f.date_to)
    if f.min_total is not None:
        stmt = stmt.where(Invoice.total >= f.min_total)
    if f.max_total is not None:
        stmt = stmt.where(Invoice.total <= f.max_total)
    if f.review_status:
        stmt = stmt.where(Invoice.review_status == f.review_status)
    if f.document_id:
        stmt = stmt.where(Invoice.document_id == f.document_id)
    return stmt


def _has_invoice_filters(f: SearchFilters) -> bool:
    return any(
        v is not None
        for v in (f.supplier, f.customer, f.invoice_number, f.currency, f.date_from, f.date_to, f.min_total,
                  f.max_total, f.review_status)
    )


def _doc_filters(stmt: Select, f: SearchFilters) -> Select:
    if f.file_type:
        stmt = stmt.where(Document.file_type == f.file_type)
    if f.document_id:
        stmt = stmt.where(Document.id == f.document_id)
    return stmt


def _invoice_summary(inv: Invoice) -> dict[str, Any]:
    return {
        "id": str(inv.id),
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
        "supplier_name": inv.supplier_name,
        "customer_name": inv.customer_name,
        "total": float(inv.total) if inv.total is not None else None,
        "currency": inv.currency,
        "review_status": inv.review_status,
    }


def _invoice_for_page(db: Session, document_id: uuid.UUID, page: int | None) -> Invoice | None:
    if page is None:
        return None
    return db.scalar(
        select(Invoice).where(
            Invoice.document_id == document_id,
            Invoice.page_start <= page,
            Invoice.page_end >= page,
        ).limit(1)
    )


def keyword_search(db: Session, q: str, f: SearchFilters, limit: int = 20) -> list[Hit]:
    hits: list[Hit] = []
    tsq = func.websearch_to_tsquery("simple", q)

    # 1) structured invoice fields (number / supplier / customer), FTS + fuzzy
    inv_rank = func.ts_rank_cd(Invoice.tsv, tsq) + func.similarity(func.coalesce(Invoice.supplier_name, ""), q)
    stmt = (
        select(Invoice, Document.original_filename, inv_rank.label("rank"))
        .join(Document, Document.id == Invoice.document_id)
        .where(
            or_(
                Invoice.tsv.op("@@")(tsq),
                Invoice.invoice_number.ilike(f"%{q}%"),
                Invoice.supplier_name.ilike(f"%{q}%"),
                Invoice.customer_name.ilike(f"%{q}%"),
            )
        )
    )
    stmt = _doc_filters(apply_invoice_filters(stmt, f), f).order_by(inv_rank.desc()).limit(limit)
    for inv, name, rank in db.execute(stmt).all():
        hits.append(Hit(
            key=f"inv:{inv.id}", document_id=inv.document_id, document_name=name, invoice_id=inv.id,
            page_number=inv.page_start,
            snippet=f"Invoice {inv.invoice_number or '?'} · {inv.supplier_name or '?'} → {inv.customer_name or '?'}",
            score=float(rank or 0) + 1.0, match="keyword", invoice=_invoice_summary(inv), sources=["fields"],
        ))

    # 2) full text of every page / sheet
    page_rank = func.ts_rank_cd(DocumentPage.tsv, tsq)
    headline = func.ts_headline(
        "simple", DocumentPage.text, tsq,
        "StartSel=<<, StopSel=>>, MaxWords=30, MinWords=12, MaxFragments=2, FragmentDelimiter= … ",
    )
    pstmt = (
        select(DocumentPage.document_id, DocumentPage.page_number, Document.original_filename, page_rank.label("rank"),
               headline.label("snippet"))
        .join(Document, Document.id == DocumentPage.document_id)
        .where(DocumentPage.tsv.op("@@")(tsq))
    )
    pstmt = _doc_filters(pstmt, f)
    if _has_invoice_filters(f):
        sub = apply_invoice_filters(select(Invoice.document_id), f)
        pstmt = pstmt.where(DocumentPage.document_id.in_(sub))
    pstmt = pstmt.order_by(page_rank.desc()).limit(limit)
    seen_invoices = {h.invoice_id for h in hits}
    for doc_id, page_no, name, rank, snippet in db.execute(pstmt).all():
        inv = _invoice_for_page(db, doc_id, page_no)
        if inv and inv.id in seen_invoices:
            continue
        hits.append(Hit(
            key=f"page:{doc_id}:{page_no}", document_id=doc_id, document_name=name,
            invoice_id=inv.id if inv else None, page_number=page_no, snippet=snippet or "",
            score=float(rank or 0), match="keyword", invoice=_invoice_summary(inv) if inv else None,
            sources=["text"],
        ))
    return hits[:limit]


def semantic_search(db: Session, q: str, f: SearchFilters, limit: int = 20) -> list[Hit]:
    from app.search.embeddings import embed_query

    qvec = embed_query(q)
    distance = Chunk.embedding.cosine_distance(qvec)
    stmt = (
        select(Chunk, Document.original_filename, distance.label("distance"))
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.embedding.is_not(None))
    )
    stmt = _doc_filters(stmt, f)
    if _has_invoice_filters(f):
        stmt = stmt.where(Chunk.document_id.in_(apply_invoice_filters(select(Invoice.document_id), f)))
    stmt = stmt.order_by(distance).limit(limit * 3)
    hits: list[Hit] = []
    seen: set[str] = set()
    for chunk, name, dist in db.execute(stmt).all():
        inv = db.get(Invoice, chunk.invoice_id) if chunk.invoice_id else _invoice_for_page(db, chunk.document_id, chunk.page_number)
        key = f"inv:{inv.id}" if inv else f"page:{chunk.document_id}:{chunk.page_number}"
        if key in seen:
            continue
        seen.add(key)
        hits.append(Hit(
            key=key, document_id=chunk.document_id, document_name=name, invoice_id=inv.id if inv else None,
            page_number=chunk.page_number, snippet=chunk.content[:280], score=round(1 - float(dist), 4),
            match="semantic", invoice=_invoice_summary(inv) if inv else None, sources=[chunk.kind],
        ))
        if len(hits) >= limit:
            break
    return hits


def hybrid_search(db: Session, q: str, f: SearchFilters, limit: int = 20, k: int = 60) -> list[Hit]:
    """Reciprocal Rank Fusion of keyword and semantic rankings."""
    kw = keyword_search(db, q, f, limit * 2)
    sem = semantic_search(db, q, f, limit * 2)
    fused: dict[str, Hit] = {}
    scores: dict[str, float] = {}
    for ranking in (kw, sem):
        for rank, hit in enumerate(ranking):
            scores[hit.key] = scores.get(hit.key, 0.0) + 1.0 / (k + rank + 1)
            if hit.key in fused:
                existing = fused[hit.key]
                existing.match = "hybrid"
                existing.sources = sorted(set(existing.sources) | set(hit.sources))
                if "<<" not in existing.snippet and "<<" in hit.snippet:
                    existing.snippet = hit.snippet
            else:
                fused[hit.key] = hit
    ordered = sorted(fused.values(), key=lambda h: scores[h.key], reverse=True)[:limit]
    for h in ordered:
        h.score = round(scores[h.key] * 100, 3)
    return ordered


def invoice_list_query(f: SearchFilters, q: str | None = None) -> Select:
    stmt = select(Invoice).join(Document, Document.id == Invoice.document_id)
    if q:
        tsq = func.websearch_to_tsquery("simple", q)
        stmt = stmt.where(or_(
            Invoice.tsv.op("@@")(tsq),
            Invoice.invoice_number.ilike(f"%{q}%"),
            Invoice.supplier_name.ilike(f"%{q}%"),
            Invoice.customer_name.ilike(f"%{q}%"),
        ))
    return _doc_filters(apply_invoice_filters(stmt, f), f)

