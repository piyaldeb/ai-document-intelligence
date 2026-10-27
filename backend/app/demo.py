"""Public-demo housekeeping: wipe all data and pre-load sample documents (daily via cron)."""

from __future__ import annotations

import logging
import time

from sqlalchemy import delete

from app.config import get_settings
from app.db import SessionLocal
from app.jobs import enqueue
from app.models import Document, DocumentStatus, Reconciliation
from app.services.ingest import ingest
from app.services.reconcile import reconcile

log = logging.getLogger(__name__)

# A tour of the features that fits a single 1-vCPU serverless invocation: several layouts,
# a scan and photos (OCR), spreadsheets, planted validation errors, a duplicate, a corrupted
# file, and a 20-invoice batch PDF + ERP export for cross-verification.
SEED = [
    "pdf/batch_march_20_invoices.pdf", "crossverify/erp_export_march.xlsx",
    "pdf/classic_01.pdf", "pdf/modern_02.pdf", "pdf/european_01.pdf", "pdf/receipt_02.pdf", "pdf/statement_03.pdf",
    "spreadsheets/ap_register_2025_multisheet.xlsx", "spreadsheets/eu_invoices_semicolon_latin1.csv",
    "spreadsheets/legacy_register.xls",
    "validation/total_mismatch.pdf", "validation/line_items_mismatch.pdf", "validation/duplicate_a.pdf",
    "validation/duplicate_b_rescan.png",
    "images/receipt_clean_01.png", "images/modern_noisy_11.png", "scanned/scanned_classic_scan_01.pdf",
    "corrupted/random_bytes.pdf",
]
HEAVY_OCR = {"images/modern_noisy_11.png", "scanned/scanned_classic_scan_01.pdf"}


def data_age_hours() -> float | None:
    """Age of the oldest stored document in hours (None when there are no documents)."""
    from datetime import UTC, datetime

    from sqlalchemy import func, select

    with SessionLocal() as db:
        oldest = db.scalar(select(func.min(Document.created_at)))
    if oldest is None:
        return None
    return (datetime.now(UTC) - oldest).total_seconds() / 3600


def reset_and_seed(budget_s: float | None = None) -> dict:
    s = get_settings()
    budget_s = budget_s if budget_s is not None else s.demo_seed_budget_s
    t0 = time.monotonic()
    with SessionLocal() as db:
        db.execute(delete(Reconciliation))
        db.execute(delete(Document))  # cascades to pages, invoices, issues, history, files, chunks
        db.commit()
    seeded: dict[str, str] = {}
    seed = [r for r in SEED if s.demo_seed_set != "light" or r not in HEAVY_OCR]
    for rel in seed:
        if time.monotonic() - t0 > budget_s:
            log.warning("demo seeding stopped at the time budget")
            break
        path = s.demo_samples_dir / rel
        if not path.exists():
            continue
        with SessionLocal() as db, open(path, "rb") as fh:
            _, doc_id = ingest(db, path.name, fh)
            db.commit()
        if doc_id:
            enqueue(doc_id)  # inline on serverless: processed before the next file
            seeded[path.name] = str(doc_id)
    summary: dict = {"documents": len(seeded), "seconds": round(time.monotonic() - t0, 1)}
    left, right = seeded.get("batch_march_20_invoices.pdf"), seeded.get("erp_export_march.xlsx")
    if left and right:
        with SessionLocal() as db:
            ok = {d.status for d in db.query(Document).filter(Document.id.in_([left, right]))}
            if ok <= {DocumentStatus.COMPLETED, DocumentStatus.NEEDS_REVIEW}:
                rec = reconcile(db, left, right)
                db.commit()
                summary["cross_verification"] = rec.summary
    return summary
