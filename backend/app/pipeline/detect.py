"""File type detection by content (magic bytes), never by extension alone.

The extension is only used to disambiguate plain-text formats (CSV) that have no signature.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.pipeline.errors import CorruptedFile, EmptyDocument, UnsupportedFileType

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".xlsx", ".xls", ".csv"}

MIME = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpeg": "image/jpeg",
    "tiff": "image/tiff",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
}


@dataclass(frozen=True)
class DetectedType:
    kind: str  # pdf | image | xlsx | xls | csv
    subtype: str  # pdf | png | jpeg | tiff | xlsx | xls | csv
    mime: str


def _sniff(head: bytes) -> str | None:
    if head[:1024].find(b"%PDF-") != -1:
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "xls"  # OLE2 compound file (legacy Excel)
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    return None


def _looks_like_text(head: bytes) -> bool:
    if not head:
        return False
    if b"\x00" in head[:4096]:
        # UTF-16 CSV exports contain NULs; accept them only with a BOM.
        return head.startswith((b"\xff\xfe", b"\xfe\xff"))
    printable = sum(1 for b in head[:4096] if b in (9, 10, 13) or 32 <= b < 127 or b >= 128)
    return printable / max(1, len(head[:4096])) > 0.95


def detect_bytes(head: bytes, filename: str) -> DetectedType:
    """Detect type from the first bytes of a file (used at upload time)."""
    ext = Path(filename).suffix.lower()
    if not head:
        raise EmptyDocument("File is empty")
    sig = _sniff(head)
    if sig == "pdf":
        return DetectedType("pdf", "pdf", MIME["pdf"])
    if sig in ("png", "jpeg", "tiff"):
        return DetectedType("image", sig, MIME[sig])
    if sig == "xls":
        return DetectedType("xls", "xls", MIME["xls"])
    if sig == "zip":
        # Only OOXML workbooks are accepted; the worker verifies the archive members.
        if ext in (".xlsx", ".xlsm") or ext not in ALLOWED_EXTENSIONS:
            return DetectedType("xlsx", "xlsx", MIME["xlsx"])
        raise UnsupportedFileType(f"ZIP container with extension {ext!r} is not a supported spreadsheet")
    if ext == ".csv" and _looks_like_text(head):
        return DetectedType("csv", "csv", MIME["csv"])
    if ext in ALLOWED_EXTENSIONS:
        # Right extension, wrong/unknown content: a damaged or mislabeled file.
        raise CorruptedFile(f"Content does not match a valid {ext} file (unrecognized signature)")
    raise UnsupportedFileType(f"Unsupported file type {ext or '(none)'}")


def detect_file(path: Path, filename: str) -> DetectedType:
    with open(path, "rb") as fh:
        head = fh.read(8192)
    detected = detect_bytes(head, filename)
    if detected.kind == "xlsx":
        try:
            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
        except zipfile.BadZipFile as exc:
            raise CorruptedFile(f"Spreadsheet archive is damaged: {exc}") from exc
        if "xl/workbook.xml" not in names:
            raise UnsupportedFileType("ZIP archive is not an Excel workbook")
    return detected
