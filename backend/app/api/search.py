from __future__ import annotations

import time
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.schemas import SearchHitOut, SearchResponse
from app.search.service import SearchFilters, hybrid_search, keyword_search, semantic_search

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, max_length=500),
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid",
    supplier: str | None = Query(None, max_length=200),
    currency: str | None = Query(None, max_length=3),
    date_from: date | None = None,
    date_to: date | None = None,
    min_total: Decimal | None = None,
    max_total: Decimal | None = None,
    review_status: str | None = Query(None, pattern="^(ok|needs_review|approved)$"),
    file_type: str | None = None,
    document_id: uuid.UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SearchResponse:
    """Search processed documents: `keyword` (full-text + fuzzy fields), `semantic`
    (vector similarity over embedded chunks) or `hybrid` (reciprocal rank fusion)."""
    if mode != "keyword" and not get_settings().embeddings_enabled:
        raise HTTPException(400, "Semantic search is disabled on this deployment")
    f = SearchFilters(supplier=supplier, currency=currency, date_from=date_from, date_to=date_to,
                      min_total=min_total, max_total=max_total, review_status=review_status,
                      file_type=file_type, document_id=document_id)
    t0 = time.perf_counter()
    fn = {"keyword": keyword_search, "semantic": semantic_search, "hybrid": hybrid_search}[mode]
    hits = fn(db, q.strip(), f, limit)
    return SearchResponse(
        query=q, mode=mode, took_ms=int((time.perf_counter() - t0) * 1000),
        results=[SearchHitOut(document_id=h.document_id, document_name=h.document_name, invoice_id=h.invoice_id,
                              page_number=h.page_number, snippet=h.snippet, score=h.score, match=h.match,
                              sources=h.sources, invoice=h.invoice) for h in hits],
    )
