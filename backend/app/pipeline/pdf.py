"""PDF text extraction: text layer for digital pages, OCR for scanned/image-only pages.

Scales to large (1000+ page) files: pages are streamed, digital pages are read in a
few ms each, and scanned pages are rendered sequentially (PyMuPDF is not thread-safe)
and OCR'd in a bounded thread pool (Tesseract runs as a subprocess, so threads give
real CPU parallelism while keeping memory bounded).
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path

import pymupdf as fitz
from PIL import Image

from app.config import get_settings
from app.pipeline.errors import CorruptedFile, EmptyDocument, EncryptedFile, TooLarge
from app.pipeline.layout import words_to_text
from app.pipeline.ocr import ocr_image
from app.pipeline.types import PageResult, ProgressFn, TextExtraction

log = logging.getLogger(__name__)
fitz.TOOLS.mupdf_display_errors(False)


def _text_layer_ok(text: str, min_chars: int) -> bool:
    stripped = re.sub(r"\s+", "", text)
    if len(stripped) < min_chars:
        return False
    # Broken font encodings produce (cid:NN) runs or replacement characters.
    bad = stripped.count("�") + len(re.findall(r"\(cid:\d+\)", text)) * 6
    alnum = sum(ch.isalnum() for ch in stripped)
    return bad / len(stripped) < 0.1 and alnum / len(stripped) > 0.4


def _render(page: fitz.Page, dpi: int) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def open_pdf(path: Path) -> fitz.Document:
    try:
        doc = fitz.open(path, filetype="pdf")
    except Exception as exc:  # fitz raises FileDataError / RuntimeError subclasses
        raise CorruptedFile(f"PDF could not be opened: {exc}") from exc
    if doc.needs_pass and not doc.authenticate(""):
        raise EncryptedFile("PDF is password protected")
    if doc.page_count == 0:
        raise EmptyDocument("PDF has no pages")
    return doc


def extract_pdf(path: Path, progress: ProgressFn | None = None) -> TextExtraction:
    s = get_settings()
    doc = open_pdf(path)
    total = doc.page_count
    if total > s.max_pdf_pages:
        raise TooLarge(f"PDF has {total} pages (limit {s.max_pdf_pages})")
    meta = {"page_count": total, "repaired": bool(getattr(doc, "is_repaired", False))}
    warnings = ["PDF structure was damaged and has been repaired"] if meta["repaired"] else []

    results: dict[int, PageResult] = {}
    done = 0
    pending: dict[Future, int] = {}
    ocr_started = 0

    def _collect(fut_set) -> None:
        nonlocal done
        for fut in fut_set:
            idx = pending.pop(fut)
            try:
                r = fut.result()
                results[idx] = PageResult(idx + 1, r.text, "ocr", r.confidence, warnings=r.warnings)
            except Exception as exc:  # one bad page must not fail a 1000-page document
                log.warning("OCR failed on page %s: %s", idx + 1, exc)
                results[idx] = PageResult(idx + 1, "", "ocr", 0.0, warnings=[f"OCR failed: {exc}"])
            done += 1
            if progress:
                progress(done, total)

    with ThreadPoolExecutor(max_workers=s.ocr_workers) as pool:
        for idx in range(total):
            try:
                page = doc.load_page(idx)
                words = page.get_text("words")
                text = words_to_text((w[0], w[1], w[2], w[3], w[4]) for w in words)
            except Exception as exc:
                results[idx] = PageResult(idx + 1, "", "text_layer", warnings=[f"page unreadable: {exc}"])
                done += 1
                continue
            if _text_layer_ok(text, s.min_text_chars_per_page):
                results[idx] = PageResult(idx + 1, text, "text_layer")
                done += 1
                if progress and (done % 25 == 0 or done == total):
                    progress(done, total)
                continue
            if s.max_ocr_pages and ocr_started >= s.max_ocr_pages:
                # Small deployments cap OCR work per document; the page is kept, flagged, not failed.
                results[idx] = PageResult(idx + 1, text, "text_layer",
                                          warnings=[f"OCR skipped: limit of {s.max_ocr_pages} scanned pages per document"])
                done += 1
                continue
            ocr_started += 1
            try:
                img = _render(page, s.ocr_dpi)
            except Exception as exc:
                results[idx] = PageResult(idx + 1, text, "text_layer", warnings=[f"render failed: {exc}"])
                done += 1
                continue
            pending[pool.submit(ocr_image, img)] = idx
            # Back-pressure: keep at most 2x workers rendered pages in memory.
            while len(pending) >= s.ocr_workers * 2:
                finished, _ = wait(list(pending), return_when=FIRST_COMPLETED)
                _collect(finished)
        while pending:
            finished, _ = wait(list(pending), return_when=FIRST_COMPLETED)
            _collect(finished)
    doc.close()

    pages = [results[i] for i in range(total)]
    meta["ocr_pages"] = sum(1 for p in pages if p.method == "ocr")
    if not any(p.text.strip() for p in pages):
        warnings.append("no text could be extracted from any page")
    return TextExtraction(pages=pages, warnings=warnings, meta=meta)
