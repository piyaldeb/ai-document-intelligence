"""XLSX / XLS / CSV parsing with pandas.

* every sheet becomes one "page" (rendered text, used for search and form-style sheets)
* the header row is detected (it is often not row 1: titles, logos, blank rows above it)
* encodings and delimiters of CSV files are sniffed; malformed rows are skipped and counted
"""

from __future__ import annotations

import csv
import io
import math
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from charset_normalizer import from_bytes

from app.config import get_settings
from app.extraction.columns import header_score
from app.pipeline.errors import CorruptedFile, EmptyDocument, EncryptedFile
from app.pipeline.types import PageResult, ProgressFn, SheetTable, TextExtraction

MAX_TEXT_CHARS_PER_SHEET = 2_000_000


def _clean_cell(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat() if v.time() == datetime.min.time() else v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return str(int(v))
    return str(v)


def _sniff_delimiter(sample: str) -> str:
    """Pick the delimiter that splits most lines into the same (>1) number of fields.

    csv.Sniffer is easily fooled by decimal commas (1.234,56) in semicolon files.
    """
    lines = [ln for ln in sample.splitlines() if ln.strip()][:60]
    best, best_score = ",", -1.0
    for d in (",", ";", "\t", "|"):
        counts = [len(row) for row in csv.reader(lines, delimiter=d)]
        if not counts:
            continue
        mode = max(set(counts), key=counts.count)
        if mode < 2:
            continue
        score = counts.count(mode) / len(counts) * 10 + min(mode, 30) / 30
        if score > best_score:
            best, best_score = d, score
    return best


def _read_csv(path: Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    raw = path.read_bytes()
    if not raw.strip():
        raise EmptyDocument("CSV file is empty")
    warnings: list[str] = []
    best = from_bytes(raw[:200_000]).best()
    encoding = best.encoding if best else "utf-8"
    try:
        text = raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        text = raw.decode("utf-8", errors="replace")
        warnings.append("CSV encoding could not be detected reliably; undecodable bytes were replaced")
    delimiter = _sniff_delimiter(text[:50_000])
    bad_lines: list[int] = []

    def _on_bad(line: list[str]) -> None:
        bad_lines.append(1)
        return None

    try:
        df = pd.read_csv(
            io.StringIO(text),
            sep=delimiter,
            header=None,
            dtype=str,
            keep_default_na=False,
            engine="python",
            on_bad_lines=_on_bad,
            skip_blank_lines=True,
        )
    except pd.errors.EmptyDataError as exc:
        raise EmptyDocument("CSV file has no rows") from exc
    except Exception as exc:
        raise CorruptedFile(f"CSV could not be parsed: {exc}") from exc
    if bad_lines:
        warnings.append(f"{len(bad_lines)} malformed CSV row(s) were skipped")
    return {"CSV": df}, warnings


def _read_excel(path: Path, kind: str) -> tuple[dict[str, pd.DataFrame], list[str]]:
    engine = "openpyxl" if kind == "xlsx" else "xlrd"
    try:
        sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=object, engine=engine)
    except zipfile.BadZipFile as exc:
        raise CorruptedFile(f"Workbook archive is damaged: {exc}") from exc
    except Exception as exc:
        msg = str(exc)
        if "encrypt" in msg.lower() or "password" in msg.lower():
            raise EncryptedFile("Workbook is password protected") from exc
        raise CorruptedFile(f"Workbook could not be read: {msg[:300]}") from exc
    return sheets, []


def _detect_header(rows: list[list[Any]]) -> int | None:
    best_idx, best_score = None, 0
    for i, row in enumerate(rows[:30]):
        cells = [c for c in row if c is not None]
        if len(cells) < 2:
            continue
        str_cells = [c for c in cells if isinstance(c, str) and not c.replace(".", "").replace(",", "").isdigit()]
        known = sum(header_score(c) for c in str_cells)
        score = known * 2 + len(str_cells) if len(str_cells) >= 2 else 0
        # A header is followed by data; a title row usually has a single cell.
        if score > best_score and known >= 2:
            best_idx, best_score = i, score
    return best_idx


def _to_table(name: str, df: pd.DataFrame, max_rows: int) -> SheetTable:
    warnings: list[str] = []
    df = df.dropna(how="all").dropna(axis=1, how="all")
    rows = [[_clean_cell(v) for v in r] for r in df.itertuples(index=False, name=None)]
    row_numbers = [int(i) + 1 for i in df.index]
    rows_and_numbers = [(r, n) for r, n in zip(rows, row_numbers) if any(c is not None for c in r)]
    if len(rows_and_numbers) > max_rows:
        warnings.append(f"sheet truncated to {max_rows} rows")
        rows_and_numbers = rows_and_numbers[:max_rows]
    rows = [r for r, _ in rows_and_numbers]
    numbers = [n for _, n in rows_and_numbers]
    h = _detect_header(rows)
    if h is None:
        return SheetTable(name, [], rows, None, numbers[0] if numbers else 1, warnings)
    header = [_fmt(c) for c in rows[h]]
    data = rows[h + 1:]
    first = numbers[h + 1] if h + 1 < len(numbers) else numbers[h] + 1
    return SheetTable(name, header, data, h, first, warnings, preamble=rows[:h])


def _render(table: SheetTable) -> str:
    """Fixed-width rendering: columns padded to a common width and separated by 2+ spaces,
    so the text extractors see the same layout conventions as PDF/OCR text."""
    rows = [list(r) for r in table.preamble]
    if table.header:
        rows.append(list(table.header))
    rows.extend(list(r) for r in table.rows)
    cells = [[_fmt(c) for c in r] for r in rows]
    n_cols = max((len(r) for r in cells), default=0)
    widths = [0] * n_cols
    for r in cells[:5000]:
        for i, c in enumerate(r):
            widths[i] = min(40, max(widths[i], len(c)))
    lines, size = [], 0
    for r in cells:
        line = "  ".join(c.ljust(widths[i]) for i, c in enumerate(r)).rstrip()
        size += len(line) + 1
        if size > MAX_TEXT_CHARS_PER_SHEET:
            break
        lines.append(line)
    return "\n".join(lines).strip("\n")


def extract_spreadsheet(path: Path, kind: str, progress: ProgressFn | None = None) -> TextExtraction:
    s = get_settings()
    if kind == "csv":
        frames, warnings = _read_csv(path)
    else:
        frames, warnings = _read_excel(path, kind)
    if not frames:
        raise EmptyDocument("Workbook has no sheets")

    pages: list[PageResult] = []
    tables: list[SheetTable] = []
    total = len(frames)
    for i, (name, df) in enumerate(frames.items()):
        table = _to_table(str(name), df, s.max_sheet_rows)
        tables.append(table)
        text = _render(table)
        pages.append(PageResult(i + 1, text, "spreadsheet", sheet_name=str(name), warnings=table.warnings))
        if progress:
            progress(i + 1, total)
    if not any(t.rows or t.header for t in tables):
        raise EmptyDocument("Spreadsheet contains no data")
    return TextExtraction(
        pages=pages,
        sheets=tables,
        warnings=warnings,
        meta={"page_count": total, "sheets": [t.name for t in tables], "rows": sum(len(t.rows) for t in tables)},
    )
