"""Split a multi-page document into invoice segments.

Large PDFs (hundreds/thousands of pages) are typically batches of many invoices. A new
segment starts on a page that
  * says "Page 1 of N", or
  * carries a different invoice number than the current segment, or
  * carries an invoice title + number after the current segment already printed its total.
Pages without their own signals (continuation pages) stay with the current segment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.extraction.normalize import normalize_invoice_number
from app.extraction.rules import page_signals
from app.pipeline.types import PageResult


@dataclass
class PageSegment:
    pages: list[PageResult] = field(default_factory=list)
    invoice_number: str | None = None
    closed: bool = False  # a total was printed

    @property
    def page_numbers(self) -> list[int]:
        return [p.page_number for p in self.pages]

    @property
    def text(self) -> str:
        return "\f".join(p.text for p in self.pages)


def segment_pages(pages: list[PageResult]) -> list[PageSegment]:
    segments: list[PageSegment] = []
    current: PageSegment | None = None
    for page in pages:
        sig = page_signals(page.text) if page.text.strip() else None
        start_new = current is None
        if sig and current is not None:
            inv = normalize_invoice_number(sig["invoice_number"])
            cur = normalize_invoice_number(current.invoice_number)
            if sig["page_of"] and sig["page_of"][0] == 1:
                start_new = True
            elif inv and cur and inv != cur:
                start_new = True
            elif inv and not cur and current.closed:
                start_new = True
            elif sig["has_title"] and current.closed and sig["chars"] > 200 and not sig["page_of"]:
                start_new = True
        if start_new:
            current = PageSegment()
            segments.append(current)
        assert current is not None
        current.pages.append(page)
        if sig:
            if sig["invoice_number"] and not current.invoice_number:
                current.invoice_number = sig["invoice_number"]
            if sig["has_total"]:
                current.closed = True
    # Drop segments that contain no text at all (blank separator sheets).
    return [s for s in segments if s.text.strip()] or segments[:1]
