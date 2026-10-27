from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import get_db
from app.models import Document, DocumentStatus
from app.pipeline.detect import ALLOWED_EXTENSIONS, detect_bytes
from app.pipeline.errors import ProcessingError
from app.schemas import (
    DocumentDetail,
    DocumentList,
    DocumentStatusOut,
    DocumentSummary,
    Page,
    PageOut,
    ReprocessResponse,
    UploadResponse,
    UploadResult,
)
from app.storage import UploadTooLarge, delete_file, save_stream
from app.worker.celery_app import enqueue

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])
jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _safe_name(name: str | None) -> str:
    base = Path(name or "upload").name.replace("\x00", "")
    return base[:255] or "upload"


@router.post("", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_documents(files: list[UploadFile] = File(...), db: Session = Depends(get_db)) -> UploadResponse:
    """Upload one or more files. Each accepted file is queued for background processing."""
    s = get_settings()
    if len(files) > s.max_files_per_request:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"At most {s.max_files_per_request} files per request")
    results: list[UploadResult] = []
    to_enqueue: list[uuid.UUID] = []
    for upload in files:
        name = _safe_name(upload.filename)
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            results.append(UploadResult(filename=name, accepted=False,
                                        error=f"Unsupported file type '{ext or 'none'}'. Allowed: "
                                              + ", ".join(sorted(ALLOWED_EXTENSIONS))))
            continue
        try:
            path, size, sha256, head = save_stream(upload.file, s.max_upload_mb * 1024 * 1024, ext)
        except UploadTooLarge as exc:
            results.append(UploadResult(filename=name, accepted=False, error=str(exc)))
            continue
        # Fast content check at the door: reject unsupported/empty files immediately. Files with a
        # valid extension but damaged content are accepted and fail visibly in the pipeline
        # (with CORRUPTED_FILE) so the user can see and reprocess them.
        try:
            detected = detect_bytes(head, name)
            kind, mime = detected.kind, detected.mime
        except ProcessingError as exc:
            if exc.code in ("UNSUPPORTED_FILE_TYPE", "EMPTY_DOCUMENT"):
                delete_file(path)
                results.append(UploadResult(filename=name, accepted=False, error=str(exc)))
                continue
            kind, mime = ("image" if ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff") else ext.lstrip(".")), "application/octet-stream"
        duplicate_of = db.scalar(
            select(Document.id).where(Document.sha256 == sha256).order_by(Document.created_at).limit(1)
        )
        doc = Document(
            original_filename=name, file_type=kind, mime_type=mime, size_bytes=size, sha256=sha256,
            storage_path=str(path), status=DocumentStatus.QUEUED, stage="queued", duplicate_of_id=duplicate_of,
        )
        db.add(doc)
        db.flush()
        to_enqueue.append(doc.id)
        results.append(UploadResult(filename=name, accepted=True, document_id=doc.id, duplicate_of=duplicate_of))
    db.commit()
    for doc_id in to_enqueue:
        enqueue(doc_id)
    accepted = sum(r.accepted for r in results)
    return UploadResponse(accepted=accepted, rejected=len(results) - accepted, results=results)


@router.get("", response_model=DocumentList)
def list_documents(
    status_: str | None = Query(None, alias="status"),
    file_type: str | None = None,
    q: str | None = Query(None, max_length=200, description="filename contains"),
    ids: str | None = Query(None, description="comma-separated ids (for progress polling)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
) -> DocumentList:
    stmt = select(Document)
    if status_:
        stmt = stmt.where(Document.status.in_(status_.split(",")))
    if file_type:
        stmt = stmt.where(Document.file_type == file_type)
    if q:
        stmt = stmt.where(Document.original_filename.ilike(f"%{q}%"))
    if ids:
        try:
            stmt = stmt.where(Document.id.in_([uuid.UUID(i) for i in ids.split(",") if i][:200]))
        except ValueError as exc:
            raise HTTPException(422, "ids must be UUIDs") from exc
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return DocumentList(items=[DocumentSummary.model_validate(r) for r in rows],
                        meta=Page(total=total, page=page, page_size=page_size))


def _get_doc(db: Session, document_id: uuid.UUID) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> DocumentDetail:
    doc = db.scalar(
        select(Document).where(Document.id == document_id).options(
            selectinload(Document.pages), selectinload(Document.invoices), selectinload(Document.events),
            selectinload(Document.issues),
        )
    )
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    out = DocumentDetail.model_validate(doc)
    out.issues = [i for i in out.issues if i.invoice_id is None]  # invoice issues live on the invoice
    return out


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
def get_status(document_id: uuid.UUID, db: Session = Depends(get_db)) -> DocumentStatusOut:
    return DocumentStatusOut.model_validate(_get_doc(db, document_id))


@router.get("/{document_id}/pages", response_model=list[PageOut])
def get_pages(
    document_id: uuid.UUID,
    page_from: int = Query(1, ge=1),
    page_to: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
) -> list[PageOut]:
    """Extracted text per page (or per sheet for spreadsheets)."""
    doc = _get_doc(db, document_id)
    page_to = page_to or page_from + 49
    pages = [p for p in doc.pages if page_from <= p.page_number <= min(page_to, page_from + 199)]
    return [PageOut(page_number=p.page_number, sheet_name=p.sheet_name, method=p.method,
                    ocr_confidence=p.ocr_confidence, char_count=p.char_count, warnings=p.warnings, text=p.text)
            for p in pages]


@router.get("/{document_id}/file")
def download_file(document_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    doc = _get_doc(db, document_id)
    path = Path(doc.storage_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stored file is missing")
    inline = doc.file_type in ("pdf", "image") and doc.mime_type != "application/octet-stream"
    return FileResponse(
        path, media_type=doc.mime_type if inline else "application/octet-stream",
        filename=doc.original_filename, content_disposition_type="inline" if inline else "attachment",
        headers={"Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/{document_id}/reprocess", response_model=ReprocessResponse, status_code=status.HTTP_202_ACCEPTED)
def reprocess(document_id: uuid.UUID, db: Session = Depends(get_db)) -> ReprocessResponse:
    doc = _get_doc(db, document_id)
    if doc.status in DocumentStatus.ACTIVE and doc.stage not in (None, "queued"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is currently being processed")
    doc.status, doc.stage, doc.progress = DocumentStatus.QUEUED, "queued", 0
    doc.error_code = doc.error_message = None
    db.commit()
    enqueue(doc.id)
    return ReprocessResponse(queued=[doc.id])


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    doc = _get_doc(db, document_id)
    if doc.status == DocumentStatus.PROCESSING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is currently being processed")
    path = doc.storage_path
    db.delete(doc)
    db.commit()
    delete_file(path)


@jobs_router.get("", response_model=DocumentList)
def list_jobs(
    status_: str = Query("failed", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> DocumentList:
    """Processing jobs by status (default: failed jobs that can be reprocessed)."""
    return list_documents(status_=status_, file_type=None, q=None, ids=None, page=page, page_size=page_size, db=db)


@jobs_router.post("/retry-failed", response_model=ReprocessResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_failed(db: Session = Depends(get_db)) -> ReprocessResponse:
    docs = db.scalars(select(Document).where(Document.status == DocumentStatus.FAILED).limit(500)).all()
    for d in docs:
        d.status, d.stage, d.progress, d.error_code, d.error_message = DocumentStatus.QUEUED, "queued", 0, None, None
    db.commit()
    for d in docs:
        enqueue(d.id)
    return ReprocessResponse(queued=[d.id for d in docs])

