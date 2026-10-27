from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text

from app.api import documents, invoices, reconciliation, search, stats
from app.config import get_settings
from app.db import engine
from app.security import SecurityHeadersMiddleware, rate_limit

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()
log = logging.getLogger(__name__)


def _warm_up_embeddings() -> None:
    try:
        from app.search.embeddings import embed_query

        embed_query("warm up")
    except Exception:  # search still works; the first query just pays the model load
        log.exception("embedding warm-up failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load the embedding model in the background so the first semantic search is fast.
    if settings.embeddings_enabled:
        threading.Thread(target=_warm_up_embeddings, daemon=True).start()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Document Intelligence API",
    version="1.0.0",
    # Served under /api so the web app's same-origin proxy also exposes the interactive docs.
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
    description="Upload invoices, receipts, scanned PDFs, images and spreadsheets; extract, validate, "
    "search and cross-verify financial data.",
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["X-API-Key", "Content-Type"],
)

protected = [Depends(rate_limit)]
for module in (documents, invoices, search, reconciliation, stats):
    app.include_router(module.router, dependencies=protected)
app.include_router(documents.jobs_router, dependencies=protected)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "extraction_provider": settings.effective_provider,
        "demo_mode": settings.demo_mode,
        "demo_reset_hours": settings.demo_reset_hours,
        "max_upload_mb": settings.max_upload_mb,
    }
