"""End-to-end processing of one document; executed by the Celery worker.

detect -> extract text (text layer / OCR / spreadsheet) -> segment -> AI extraction ->
validate -> index (chunks + embeddings) -> finalize

Every stage is recorded in `processing_events` (processing history), progress is committed
as it advances so the UI can poll it, and the task is idempotent: a re-run deletes the
previous attempt's outputs first, so failed jobs can be reprocessed safely.
"""

from __future__ import annotations

import logging
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, update

from app.config import get_settings
from app.db import SessionLocal
from app.extraction import service as extraction
from app.extraction.rules import page_signals
from app.extraction.schema import InvoiceData
from app.extraction.spreadsheet_mapper import map_sheet
from app.models import (
    Chunk,
    Document,
    DocumentPage,
    DocumentStatus,
    Invoice,
    ProcessingEvent,
    ValidationIssue,
)
from app.pipeline.detect import detect_file
from app.pipeline.errors import ProcessingError
from app.pipeline.images import extract_image
from app.pipeline.pdf import extract_pdf
from app.pipeline.segment import segment_pages
from app.pipeline.spreadsheet import extract_spreadsheet
from app.pipeline.types import TextExtraction
from app.services.invoices import create_invoice, refresh_document_rollup

log = logging.getLogger(__name__)

STAGE_RANGES = {
    "detect": (0, 3),
    "extract_text": (3, 60),
    "segment": (60, 62),
    "ai_extraction": (62, 85),
    "validate": (85, 99),
}
INVOICE_COMMIT_BATCH = 200
MAX_INDEXED_CHUNKS = 5000


class Job:
    def __init__(self, document_id: uuid.UUID, attempt: int):
        self.document_id = document_id
        self.attempt = attempt
        self._last_progress_write = 0.0

    def event(self, stage: str, status: str, message: str | None = None, duration_ms: int | None = None,
              details: dict | None = None) -> None:
        with SessionLocal() as db:
            db.add(ProcessingEvent(document_id=self.document_id, attempt=self.attempt, stage=stage, status=status,
                                   message=message, duration_ms=duration_ms, details=details or {}))
            db.commit()

    def progress(self, stage: str, fraction: float, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_progress_write < 0.7:
            return
        self._last_progress_write = now
        lo, hi = STAGE_RANGES.get(stage, (0, 100))
        pct = int(lo + (hi - lo) * max(0.0, min(1.0, fraction)))
        with SessionLocal() as db:
            db.execute(update(Document).where(Document.id == self.document_id).values(stage=stage, progress=pct))
            db.commit()

    @contextmanager
    def stage(self, name: str, **details):
        self.progress(name, 0.0, force=True)
        self.event(name, "started", details=details or None)
        t0 = time.perf_counter()
        try:
            yield
        except Exception as exc:
            self.event(name, "failed", str(exc)[:1000], int((time.perf_counter() - t0) * 1000))
            raise
        self.event(name, "completed", duration_ms=int((time.perf_counter() - t0) * 1000))


def _reset_outputs(document_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        for model in (Chunk, ValidationIssue, Invoice, DocumentPage):
            db.execute(delete(model).where(model.document_id == document_id))
        db.commit()


def _extract_text(path: Path, kind: str, job: Job) -> TextExtraction:
    def on_progress(done: int, total: int) -> None:
        job.progress("extract_text", done / max(1, total))

    if kind == "pdf":
        return extract_pdf(path, on_progress)
    if kind == "image":
        return extract_image(path, on_progress)
    return extract_spreadsheet(path, kind, on_progress)


class _Unit:
    """One invoice candidate to extract: text segment or a spreadsheet-mapped record."""

    def __init__(self, text: str, source_ref: dict, ocr_conf: float | None, data: InvoiceData | None = None):
        self.text = text
        self.source_ref = source_ref
        self.ocr_conf = ocr_conf
        self.data = data


def build_units(extraction_result: TextExtraction) -> list[_Unit]:
    """Turn extracted pages/sheets into invoice candidates."""
    units: list[_Unit] = []
    if extraction_result.sheets:
        for page, table in zip(extraction_result.pages, extraction_result.sheets):
            mapped = map_sheet(table)
            if mapped:
                for m in mapped:
                    units.append(_Unit("", {"sheet": table.name, "rows": [m.rows[0], m.rows[-1]],
                                            "pages": [page.page_number]}, None, m.data))
            elif page.text.strip():
                # Form-style sheet: only treat it as an invoice if it looks like one (a notes or
                # summary tab next to a register must not become a phantom invoice).
                sig = page_signals(page.text)
                if sig["invoice_number"] or sig["has_total"] or sig["has_title"]:
                    units.append(_Unit(page.text, {"sheet": table.name, "pages": [page.page_number]}, None))
    else:
        for seg in segment_pages(extraction_result.pages):
            confs = [p.ocr_confidence for p in seg.pages if p.ocr_confidence is not None]
            units.append(_Unit(seg.text, {"pages": seg.page_numbers}, min(confs) if confs else None))
    return units


def run(document_id: uuid.UUID) -> str:
    """Process a document. Returns the final status. Raises ProcessingError if retryable."""
    s = get_settings()
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            log.warning("document %s no longer exists", document_id)
            return "missing"
        doc.status = DocumentStatus.PROCESSING
        doc.stage = "queued"
        doc.progress = 0
        doc.attempts += 1
        doc.error_code = doc.error_message = None
        doc.processing_started_at = datetime.now(UTC)
        doc.processing_finished_at = None
        attempt = doc.attempts
        path, filename = Path(doc.storage_path), doc.original_filename
        db.commit()

    job = Job(document_id, attempt)
    t_start = time.perf_counter()
    _reset_outputs(document_id)
    provider = s.effective_provider
    try:
        with job.stage("detect"):
            if not path.exists():
                raise ProcessingError("Stored file is missing", code="FILE_MISSING")
            detected = detect_file(path, filename)

        with job.stage("extract_text", kind=detected.kind):
            extraction_result = _extract_text(path, detected.kind, job)
            with SessionLocal() as db:
                db.add_all(
                    DocumentPage(document_id=document_id, page_number=p.page_number, sheet_name=p.sheet_name,
                                 method=p.method, text=p.text.replace("\x00", ""), ocr_confidence=p.ocr_confidence,
                                 char_count=len(p.text), warnings=p.warnings)
                    for p in extraction_result.pages
                )
                db.execute(update(Document).where(Document.id == document_id).values(
                    page_count=len(extraction_result.pages), mime_type=detected.mime,
                    meta={**extraction_result.meta, "warnings": extraction_result.warnings},
                ))
                db.commit()

        with job.stage("segment"):
            units = build_units(extraction_result)
            job.event("segment", "info", f"{len(units)} invoice candidate(s) found")

        with job.stage("ai_extraction", provider=provider, candidates=len(units)):
            pending = [u for u in units if u.data is None]
            done = 0

            def _extract(u: _Unit) -> InvoiceData:
                ctx = f" (pages {u.source_ref['pages'][0]}-{u.source_ref['pages'][-1]} of {filename})" if u.source_ref.get("pages") else ""
                return extraction.extract_text(u.text, provider=provider, context=ctx)

            workers = s.llm_max_concurrency if provider == "anthropic" else 1
            with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
                for u, data in zip(pending, pool.map(_extract, pending)):
                    u.data = data
                    done += 1
                    job.progress("ai_extraction", done / max(1, len(pending)))
            if any("LLM extraction unavailable" in n for u in pending for n in (u.data.notes if u.data else [])):
                job.event("ai_extraction", "info", "LLM unavailable for some candidates; rules extractor used")

        with job.stage("validate"):
            with SessionLocal() as db:
                doc = db.get(Document, document_id)
                for i, u in enumerate(units, start=1):
                    assert u.data is not None
                    create_invoice(db, doc, u.data, sequence=i, source_ref=u.source_ref,
                                   source_text=u.text, min_ocr_confidence=u.ocr_conf)
                    if i % INVOICE_COMMIT_BATCH == 0:
                        db.commit()  # releases advisory locks in long batches
                        job.progress("validate", i / len(units))
                if not units:
                    db.add(ValidationIssue(document_id=document_id, code="NO_INVOICE_FOUND", severity="warning",
                                           message="No invoice content could be identified in this document"))
                if doc.duplicate_of_id:
                    db.add(ValidationIssue(document_id=document_id, code="DUPLICATE_FILE", severity="warning",
                                           message="An identical file was uploaded before",
                                           details={"document_id": str(doc.duplicate_of_id)}))
                db.commit()

        with SessionLocal() as db:
            doc = db.get(Document, document_id)
            doc.status = DocumentStatus.COMPLETED
            refresh_document_rollup(db, doc)
            doc.stage = "done"
            doc.progress = 100
            doc.extraction_provider = provider
            doc.processing_finished_at = datetime.now(UTC)
            doc.processing_ms = int((time.perf_counter() - t_start) * 1000)
            final = doc.status
            db.commit()
        job.event("finalize", "completed", f"status={final}", int((time.perf_counter() - t_start) * 1000))
        # Results are final and visible now; the semantic index is built off the critical path.
        if s.embeddings_enabled:
            schedule_indexing(document_id)
        return final

    except ProcessingError as exc:
        _fail(document_id, exc.code, str(exc), t_start)
        if exc.retryable:
            raise
        return DocumentStatus.FAILED
    except Exception as exc:  # unexpected bug: keep the traceback in the history, not in the API message
        log.exception("processing failed for %s", document_id)
        job.event("error", "failed", "internal error", details={"traceback": traceback.format_exc()[-4000:]})
        _fail(document_id, "INTERNAL_ERROR", f"Unexpected processing error ({type(exc).__name__})", t_start)
        return DocumentStatus.FAILED


def _fail(document_id: uuid.UUID, code: str, message: str, t_start: float) -> None:
    with SessionLocal() as db:
        db.execute(update(Document).where(Document.id == document_id).values(
            status=DocumentStatus.FAILED, error_code=code, error_message=message[:2000], stage="failed",
            processing_finished_at=datetime.now(UTC), processing_ms=int((time.perf_counter() - t_start) * 1000),
        ))
        db.add(ProcessingEvent(document_id=document_id, stage="finalize", status="failed", message=f"{code}: {message}"[:2000]))
        db.commit()


def _invoice_summary_text(inv: Invoice) -> str:
    parts = [
        f"Invoice {inv.invoice_number or 'unknown number'}",
        f"dated {inv.invoice_date.isoformat()}" if inv.invoice_date else "",
        f"from {inv.supplier_name}" if inv.supplier_name else "",
        f"to {inv.customer_name}" if inv.customer_name else "",
        f"total {inv.total} {inv.currency or ''}".strip() if inv.total is not None else "",
    ]
    items = "; ".join(li.description for li in inv.line_items[:15] if li.description)
    return " ".join(p for p in parts if p) + (f". Items: {items}" if items else "")


def schedule_indexing(document_id: uuid.UUID) -> None:
    """Queue semantic indexing as its own task (separate queue, scalable independently)."""
    from app.worker.celery_app import enqueue_index

    enqueue_index(document_id)


def index_document(document_id: uuid.UUID) -> int:
    """Embed invoice summaries + page text chunks of a processed document. Idempotent."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.search.embeddings import chunk_text, embed_passages

    s = get_settings()
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None or doc.status not in (DocumentStatus.COMPLETED, DocumentStatus.NEEDS_REVIEW):
            return 0
        attempt = doc.attempts
        invoices = db.scalars(
            select(Invoice).where(Invoice.document_id == document_id).options(selectinload(Invoice.line_items))
            .order_by(Invoice.sequence).limit(2000)
        ).all()
        rows: list[dict] = [
            {"invoice_id": inv.id, "page_number": inv.page_start, "kind": "invoice", "content": _invoice_summary_text(inv)}
            for inv in invoices
        ]
        pages = db.execute(
            select(DocumentPage.page_number, DocumentPage.text).where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number)
        ).all()
        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        db.commit()

    job = Job(document_id, attempt)
    job.event("index", "started")
    t0 = time.perf_counter()
    capped = False
    for page_number, text in pages:
        for chunk in chunk_text(text, s.chunk_chars, s.chunk_overlap):
            rows.append({"invoice_id": None, "page_number": page_number, "kind": "page", "content": chunk})
        if len(rows) >= MAX_INDEXED_CHUNKS:
            rows, capped = rows[:MAX_INDEXED_CHUNKS], True
            break
    batch = 256
    for start in range(0, len(rows), batch):
        part = rows[start:start + batch]
        vectors = embed_passages([r["content"] for r in part])
        with SessionLocal() as db:
            db.add_all(Chunk(document_id=document_id, embedding=v, **r) for r, v in zip(part, vectors))
            db.commit()
    ms = int((time.perf_counter() - t0) * 1000)
    job.event("index", "completed", f"{len(rows)} chunks indexed" + (" (capped)" if capped else ""), ms,
              details={"chunks": len(rows)})
    return len(rows)
