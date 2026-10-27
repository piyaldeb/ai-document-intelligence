from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

ProgressFn = Callable[[int, int], None]  # (done, total)


@dataclass
class PageResult:
    page_number: int  # 1-based (sheets: 1-based sheet index)
    text: str
    method: str  # text_layer | ocr | spreadsheet
    ocr_confidence: float | None = None
    sheet_name: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class SheetTable:
    """A parsed spreadsheet sheet: detected header + data rows (raw cell values)."""

    name: str
    header: list[str]
    rows: list[list[Any]]
    header_row_index: int | None
    first_data_row: int  # 1-based spreadsheet row number of rows[0]
    warnings: list[str] = field(default_factory=list)
    preamble: list[list[Any]] = field(default_factory=list)  # rows above the header (titles, form fields)


@dataclass
class TextExtraction:
    pages: list[PageResult]
    sheets: list[SheetTable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
