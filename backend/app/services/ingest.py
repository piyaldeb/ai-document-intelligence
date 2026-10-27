"""Accepting a file into the system (shared by the upload API and demo seeding)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, DocumentFile, DocumentStatus
from app.pipeline.detect import ALLOWED_EXTENSIONS, detect_bytes
from app.pipeline.errors import ProcessingError
from app.schemas import UploadResult
from app.storage import UploadTooLarge, delete_file, save_stream


def safe_name(name: str | None) -> str:
    base = Path(name or "upload").name.replace("\x00", "")
    return base[:255] or "upload"


def ingest(db: Session, filename: str | None, stream: BinaryIO) -> tuple[UploadResult, uuid.UUID | None]:
    """Validate and store one file and create its document row (status queued). Does not commit."""
    s = get_settings()
    name = safe_name(filename)
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return UploadResult(filename=name, accepted=False,
                            error=f"Unsupported file type '{ext or 'none'}'. Allowed: "
                                  + ", ".join(sorted(ALLOWED_EXTENSIONS))), None
    try:
        path, size, sha256, head = save_stream(stream, s.max_upload_mb * 1024 * 1024, ext)
    except UploadTooLarge as exc:
        return UploadResult(filename=name, accepted=False, error=str(exc)), None
    # Fast content check at the door: reject unsupported/empty files immediately. Files with a
    # valid extension but damaged content are accepted and fail visibly in the pipeline
    # (with CORRUPTED_FILE) so the user can see and reprocess them.
    try:
        detected = detect_bytes(head, name)
        kind, mime = detected.kind, detected.mime
    except ProcessingError as exc:
        if exc.code in ("UNSUPPORTED_FILE_TYPE", "EMPTY_DOCUMENT"):
            delete_file(path)
            return UploadResult(filename=name, accepted=False, error=str(exc)), None
        kind = "image" if ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff") else ext.lstrip(".")
        mime = "application/octet-stream"
    duplicate_of = db.scalar(select(Document.id).where(Document.sha256 == sha256).order_by(Document.created_at).limit(1))
    doc = Document(
        original_filename=name, file_type=kind, mime_type=mime, size_bytes=size, sha256=sha256,
        storage_path=str(path), status=DocumentStatus.QUEUED, stage="queued", duplicate_of_id=duplicate_of,
    )
    db.add(doc)
    db.flush()
    if s.storage_backend == "db":
        db.add(DocumentFile(document_id=doc.id, data=Path(path).read_bytes()))
    return UploadResult(filename=name, accepted=True, document_id=doc.id, duplicate_of=duplicate_of), doc.id
