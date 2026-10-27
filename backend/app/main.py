from __future__ import annotations

import logging

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
app = FastAPI(
    title="Document Intelligence API",
    version="1.0.0",
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
    return {"status": "ok", "extraction_provider": settings.effective_provider}
