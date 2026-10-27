"""Deterministic, layout-aware invoice extractor.

Used as (a) the extractor when no LLM is configured, (b) a cross-check for LLM output, and
(c) the page-level signal for splitting large multi-invoice PDFs. It never computes or
infers a value that is not printed in the document: missing fields stay None.

Input is layout text (see pipeline/layout.py): columns separated by 2+ spaces, pages
separated by form feeds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.extraction.normalize import (
    CURRENCY_CODES,
    detect_currency,
    detect_decimal_comma,
    find_amounts,
    find_dates,
    money,
    parse_amount,
)
from app.extraction.schema import InvoiceData, LineItemData

# ------------------------------------------------------------------ label vocabularies

INVOICE_NO_LABELS = [
    r"tax\s+invoice\s*(?:no\.?|number|#)",
    r"invoice\s*(?:no\.?|number|num\.?|#|id|ref(?:erence)?)",
    r"inv\.?\s*(?:no\.?|#|number)",
    r"bill\s*(?:no\.?|number|#)",
    r"receipt\s*(?:no\.?|number|#)",
    r"document\s*(?:no\.?|number|#)",
    r"invoice(?=\s*[:#])",
]
DATE_LABELS = [
    (r"invoice\s*date", 0.95),
    (r"date\s*of\s*(?:issue|invoice)", 0.95),
    (r"(?:issue|issued|billing|bill|receipt)\s*date", 0.9),
    (r"dated?", 0.8),
]
NOT_INVOICE_DATE = re.compile(r"\b(due|delivery|order|ship(?:ping|ment)?|payment|expiry|service|period|po)\s*date", re.I)
SUPPLIER_LABELS = [
    r"(?:supplier|vendor|seller|merchant)(?:\s*name)?",
    r"(?:sold|billed|issued)\s+by",
    r"from",
    r"pay\s+to",
    r"remit\s+to",
]
CUSTOMER_LABELS = [
    (r"bill(?:ed)?\s+to", 0.92),
    (r"invoice\s+to", 0.92),
    (r"sold\s+to", 0.9),
    (r"customer(?:\s*name)?", 0.9),
    (r"client(?:\s*name)?", 0.9),
    (r"buyer", 0.88),
    (r"ship\s+to", 0.6),
    (r"to", 0.7),
]
SUBTOTAL_LABELS = [
    r"sub[\s\-]?total",
    r"net\s*(?:amount|total|value)",
    r"total\s*(?:before|excl\.?|excluding|w/?o)\s*(?:tax|vat|gst)",
    r"amount\s*(?:before|excl\.?|excluding)\s*(?:tax|vat|gst)",
    r"taxable\s*(?:amount|value)",
]
TAX_LABELS = [
    r"(?:total\s*)?(?:sales\s*)?(?:tax|vat|gst|hst|igst|cgst|sgst)(?:\s*amount)?(?:\s*(?:@|at)?\s*\(?\s*\d+(?:[.,]\d+)?\s*%\s*\)?)?",
]
TOTAL_LABELS = [
    (r"grand\s*total", 0.95),
    (r"total\s*(?:amount\s*)?(?:due|payable)", 0.95),
    (r"(?:amount|balance)\s*(?:due|payable)", 0.93),
    (r"invoice\s*total", 0.95),
    (r"total\s*(?:incl\.?|including)\s*(?:tax|vat|gst)", 0.95),
    (r"total\s*amount", 0.92),
    (r"total(?:\s*\([A-Z]{3}\))?", 0.85),
]
NOT_TOTAL = re.compile(r"sub[\s\-]?total|total\s*(?:tax|vat|gst|excl|before|net|qty|quantity|items?|units|hours)", re.I)

_ALL_LABELS = (
    INVOICE_NO_LABELS + [p for p, _ in DATE_LABELS] + SUPPLIER_LABELS + [p for p, _ in CUSTOMER_LABELS]
    + SUBTOTAL_LABELS + TAX_LABELS + [p for p, _ in TOTAL_LABELS] + [r"due\s*date", r"(?:ship|delivery)\s+(?:to|date)"]
)
_LABEL_ONLY = re.compile(r"^\s*(?:" + "|".join(f"(?:{p})" for p in _ALL_LABELS) + r")\s*[:#.\-]*\s*$", re.I)

TITLE_WORDS = re.compile(
    r"^(?:tax\s+)?(?:invoice|receipt|bill|statement|credit\s+note|proforma|commercial\s+invoice|original|copy|page\s+\d+.*)$",
    re.I,
)
COMPANY_SUFFIX = re.compile(
    r"\b(ltd|limited|inc|llc|gmbh|corp|corporation|company|co\.|plc|pvt|s\.a\.|b\.v\.|ag|pte|pty|llp|srl|group|industries|enterprises|traders|solutions|services|systems)\b",
    re.I,
)
LINE_HEADER_DESC = re.compile(r"\b(description|item|product|service|particulars|details|article)s?\b", re.I)
LINE_HEADER_NUM = re.compile(r"\b(qty|quantity|hrs|hours|units?|price|rate|amount|total|cost)\b", re.I)
PAGE_MARKER = re.compile(r"\bpage\s*(\d+)\s*(?:of|/)\s*(\d+)\b", re.I)
INVOICE_NO_TOKEN = re.compile(r"^[#:\s]*(?:no\.?\s*)?([A-Za-z0-9][A-Za-z0-9\-/_.]{0,39})")


@dataclass
class Segment:
    start: int
    end: int
    text: str


def split_segments(line: str) -> list[Segment]:
    out = []
    for m in re.finditer(r"\S+(?:\s\S+)*", line):
        out.append(Segment(m.start(), m.end(), m.group(0)))
    return out


def _label_re(label: str) -> re.Pattern:
    return re.compile(rf"^\s*(?:{label})\b\s*[:#.\-–]*\s*(?P<rest>.*)$", re.I)


def _aligned_below(lines: list[str], idx: int, seg: Segment, max_down: int = 2) -> tuple[str, int] | None:
    """Text in the following line(s) that starts in the same column as `seg`."""
    for j in range(idx + 1, min(len(lines), idx + 1 + max_down)):
        if not lines[j].strip():
            continue
        for s in split_segments(lines[j]):
            if abs(s.start - seg.start) <= 6 or (s.start <= seg.start < s.end):
                return s.text, j
        return None
    return None


@dataclass
class Candidate:
    value: str
    confidence: float
    line: int
    evidence: str


def _labeled_values(lines: list[str], labels: list[tuple[str, float]], allow_below: bool = True) -> list[Candidate]:
    """Find `label: value` pairs in the same segment, the next segment, or the aligned line below."""
    compiled = [(_label_re(lbl), conf) for lbl, conf in labels]
    out: list[Candidate] = []
    for i, line in enumerate(lines):
        segs = split_segments(line)
        for k, seg in enumerate(segs):
            for rx, conf in compiled:
                m = rx.match(seg.text)
                if not m:
                    continue
                rest = m.group("rest").strip()
                if rest:
                    out.append(Candidate(rest, conf, i, line))
                elif k + 1 < len(segs) and not _LABEL_ONLY.match(segs[k + 1].text):
                    out.append(Candidate(segs[k + 1].text, conf * 0.97, i, line))
                elif allow_below:
                    below = _aligned_below(lines, i, seg)
                    if below:
                        out.append(Candidate(below[0], conf * 0.93, below[1], f"{line.strip()} / {below[0]}"))
                break
    return out


# ------------------------------------------------------------------ field extractors


def _clean_invoice_number(raw: str) -> str | None:
    m = INVOICE_NO_TOKEN.match(raw.strip())
    if not m:
        return None
    token = m.group(1).rstrip(".-/_")
    if not re.search(r"\d", token) or len(token) < 2:
        return None
    if re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", token):  # a date, not a number
        return None
    return token


def extract_invoice_number(lines: list[str]) -> Candidate | None:
    labels = [(lbl, 0.95 - i * 0.02) for i, lbl in enumerate(INVOICE_NO_LABELS)]
    for cand in _labeled_values(lines, labels):
        token = _clean_invoice_number(cand.value)
        if token:
            return Candidate(token, cand.confidence, cand.line, cand.evidence)
    return None


def extract_invoice_date(lines: list[str], dayfirst: bool) -> tuple[Candidate, bool] | None:
    best: tuple[Candidate, bool] | None = None
    for cand in _labeled_values(lines, DATE_LABELS):
        if NOT_INVOICE_DATE.search(cand.evidence.split("/")[0]):
            # e.g. "Due Date:" also matches the generic "date" label
            seg_text = cand.evidence
            if not re.search(r"invoice\s*date|date\s*of\s*issue|issue\s*date", seg_text, re.I):
                continue
        dates = find_dates(cand.value, dayfirst=dayfirst)
        if not dates:
            continue
        d = dates[0]
        c = Candidate(d.value.isoformat(), cand.confidence * (0.85 if d.ambiguous else 1.0), cand.line, cand.evidence)
        if best is None or c.confidence > best[0].confidence:
            best = (c, d.ambiguous)
    if best:
        return best
    # Fallback: first date in the top part of the document that is not labelled as due/delivery.
    for i, line in enumerate(lines[:25]):
        if NOT_INVOICE_DATE.search(line):
            continue
        dates = find_dates(line, dayfirst=dayfirst)
        if dates:
            d = dates[0]
            return Candidate(d.value.isoformat(), 0.55, i, line), d.ambiguous
    return None


def _clean_party(raw: str) -> str | None:
    s = raw.strip().strip(":,-").strip()
    s = re.split(r"\s{2,}", s)[0]
    if len(s) < 2 or not re.search(r"[A-Za-z]{2}", s):
        return None
    if re.match(r"^(?:invoice|date|no\.?|number|total|amount|address|tel|phone|email|vat|tax)\b", s, re.I):
        return None
    return s[:200]


def extract_customer(lines: list[str]) -> Candidate | None:
    cands = []
    for cand in _labeled_values(lines, CUSTOMER_LABELS):
        name = _clean_party(cand.value)
        if name:
            cands.append(Candidate(name, cand.confidence, cand.line, cand.evidence))
    if not cands:
        return None
    return max(cands, key=lambda c: (c.confidence, -c.line))


def extract_supplier(lines: list[str], customer: Candidate | None) -> Candidate | None:
    labels = [(lbl, 0.92) for lbl in SUPPLIER_LABELS]
    for cand in _labeled_values(lines, labels):
        name = _clean_party(cand.value)
        if name and (customer is None or name != customer.value):
            return Candidate(name, cand.confidence, cand.line, cand.evidence)

    # Heuristic: the first company-like line at the top of the document (letterhead).
    customer_line = customer.line if customer else None
    seen = 0
    for i, line in enumerate(lines[:20]):
        if not line.strip():
            continue
        if customer_line is not None and i >= customer_line - 1:
            break
        seen += 1
        if seen > 8:
            break
        segs = split_segments(line)
        for seg in segs[:2]:
            t = seg.text.strip()
            if TITLE_WORDS.match(t) or ":" in t or "@" in t or "www." in t.lower():
                continue
            if re.search(r"\d{3,}", t) or len(re.findall(r"[A-Za-z]", t)) < 3:
                continue
            if re.match(r"^(?:bill|ship|sold|invoice|date|to|from)\b", t, re.I):
                continue
            conf = 0.72 if COMPANY_SUFFIX.search(t) else 0.55
            return Candidate(t[:200], conf, i, line)
    return None


def _amount_after_label(lines: list[str], labels: list[tuple[str, float]], exclude: re.Pattern | None,
                        decimal_comma: bool) -> list[Candidate]:
    out = []
    compiled = [(re.compile(rf"(?:^|\s{{2,}}|^\s*)(?P<label>{lbl})\b", re.I), conf) for lbl, conf in labels]
    for i, line in enumerate(lines):
        for rx, conf in compiled:
            m = rx.search(line)
            if not m:
                continue
            label_text = m.group("label")
            if exclude and exclude.search(line[m.start(): m.end() + 12]):
                continue
            if LINE_HEADER_DESC.search(line) and LINE_HEADER_NUM.search(line):
                continue  # table header, not a totals line
            tail = line[m.end():]
            amounts = find_amounts(tail, decimal_comma)
            if not amounts and i + 1 < len(lines) and len(lines[i + 1].strip()) < 40:
                amounts = find_amounts(lines[i + 1], decimal_comma)
            if amounts:
                a = amounts[-1]
                out.append(Candidate(str(a.value), conf, i, f"{label_text} {a.raw}"))
            break
    return out


def extract_amounts(lines: list[str], decimal_comma: bool) -> dict[str, Candidate]:
    res: dict[str, Candidate] = {}
    totals = _amount_after_label(lines, TOTAL_LABELS, NOT_TOTAL, decimal_comma)
    if totals:
        # Strongest label wins; among equals, the one printed last (totals block is at the end).
        res["total"] = max(totals, key=lambda c: (c.confidence, c.line))
    subs = _amount_after_label(lines, [(lbl, 0.92) for lbl in SUBTOTAL_LABELS], None, decimal_comma)
    if subs:
        res["subtotal"] = max(subs, key=lambda c: c.line)
    taxes = _amount_after_label(
        lines, [(lbl, 0.9) for lbl in TAX_LABELS],
        re.compile(r"tax\s*(?:id|no|number|reg|registration|invoice)|vat\s*(?:id|no|number|reg)|gstin|excl|before|incl", re.I),
        decimal_comma,
    )
    if taxes:
        # Several tax lines (e.g. CGST + SGST) are reported as their printed sum only if
        # there is no single "total tax" line; we never derive tax from total - subtotal.
        explicit_total = [c for c in taxes if re.match(r"total", c.evidence, re.I)]
        if explicit_total:
            res["tax"] = explicit_total[-1]
        elif len({c.line for c in taxes}) > 1 and len(taxes) <= 3:
            s = sum(Decimal(c.value) for c in taxes)
            res["tax"] = Candidate(str(s), 0.7, taxes[-1].line, " + ".join(c.evidence for c in taxes))
        else:
            res["tax"] = taxes[-1]
    return res


# ------------------------------------------------------------------ line items


def _header_columns(line: str) -> list[tuple[Segment, str]]:
    cols = []
    for seg in split_segments(line):
        t = seg.text.lower()
        if re.search(r"qty|quantity|hrs|hours|units?\b", t):
            kind = "quantity"
        elif re.search(r"unit\s*price|price|rate|unit\s*cost|cost", t):
            kind = "unit_price"
        elif re.search(r"amount|total|line\s*total|value|ext", t):
            kind = "amount"
        elif LINE_HEADER_DESC.search(t):
            kind = "description"
        elif re.fullmatch(r"#|no\.?|sr\.?|s\.?no\.?|sl\.?|line|item\s*#", t):
            kind = "index"
        else:
            kind = "other"
        cols.append((seg, kind))
    return cols


def _is_stop_line(line: str) -> bool:
    return bool(re.match(
        r"^\s*(sub[\s\-]?total|total|grand\s*total|tax|vat|gst|amount\s*due|balance|net\s*amount|notes?|terms|payment|thank)",
        line, re.I,
    )) or bool(re.search(r"\s{2,}(sub[\s\-]?total|grand\s*total|total\s*due|amount\s*due)\b", line, re.I))


_NUM_SEG = re.compile(
    r"^(?P<code>[A-Z]{3}\s?)?[$€£₹৳¥(\-]*\s?[\d][\d,.']*\)?\s?(?P<unit>hrs?|hours|pcs|units?|ea|nos?|kg|%)?\.?$",
    re.I,
)
_PERCENT = object()


def _numeric_value(text: str, decimal_comma: bool):
    t = text.strip()
    m = _NUM_SEG.match(t)
    if not m:
        return None
    if m.group("code") and m.group("code").strip().upper() not in CURRENCY_CODES:
        return None
    if (m.group("unit") or "") == "%":
        return _PERCENT
    raw = t[len(m.group("code") or ""):]
    raw = re.sub(r"\s?(?:hrs?|hours|pcs|units?|ea|nos?|kg)\.?$", "", raw, flags=re.I)
    return parse_amount(raw, decimal_comma)


def extract_line_items(lines: list[str], decimal_comma: bool) -> list[LineItemData]:
    header_idx = None
    for i, line in enumerate(lines):
        if LINE_HEADER_DESC.search(line) and len(LINE_HEADER_NUM.findall(line)) >= 1 and len(split_segments(line)) >= 2:
            header_idx = i
            break
    if header_idx is None:
        return []
    columns = _header_columns(lines[header_idx])
    numeric_cols = [(seg, kind) for seg, kind in columns if kind in ("quantity", "unit_price", "amount")]
    first_kind = columns[0][1] if columns else None

    items: list[LineItemData] = []
    for line in lines[header_idx + 1:]:
        if not line.strip():
            continue
        if _is_stop_line(line):
            break
        if PAGE_MARKER.search(line) or re.search(r"continued", line, re.I):
            continue
        if LINE_HEADER_DESC.search(line) and LINE_HEADER_NUM.search(line):
            continue  # header repeated on a continuation page
        parsed = [(seg, _numeric_value(seg.text, decimal_comma)) for seg in split_segments(line)]
        parsed = [(seg, v) for seg, v in parsed if v is not _PERCENT]
        if (
            len(parsed) > 2
            and parsed[0][1] is not None
            and re.fullmatch(r"\d{1,3}\.?", parsed[0][0].text)
            and first_kind in ("index", "other", "description")
        ):
            parsed = parsed[1:]  # leading row number
        text_parts = [seg for seg, v in parsed if v is None]
        numeric: list[tuple[Segment, Decimal]] = [(seg, v) for seg, v in parsed if v is not None]
        description = " ".join(s.text for s in text_parts).strip() or None
        if not numeric or not text_parts:
            if not numeric and description and items and len(description) < 120:
                items[-1].description = f"{items[-1].description or ''} {description}".strip()
            continue

        item = LineItemData(description=description)
        assigned: dict[str, Decimal] = {}
        if numeric_cols and len(numeric) <= len(numeric_cols):
            for seg, val in numeric:
                centre = (seg.start + seg.end) / 2
                best = min(numeric_cols, key=lambda c: min(abs(c[0].end - seg.end), abs((c[0].start + c[0].end) / 2 - centre)))
                if best[1] not in assigned:
                    assigned[best[1]] = val
        if len(assigned) != len(numeric):
            assigned = {}
            vals = [v for _, v in numeric]
            if len(vals) >= 3:
                assigned = {"quantity": vals[-3], "unit_price": vals[-2], "amount": vals[-1]}
            elif len(vals) == 2:
                assigned = {"quantity": vals[0], "amount": vals[1]}
            else:
                assigned = {"amount": vals[0]}
        item.quantity = assigned.get("quantity")
        item.unit_price = assigned.get("unit_price")
        item.amount = money(assigned["amount"]) if "amount" in assigned else None
        items.append(item)
    return items


# ------------------------------------------------------------------ entry point


def extract(text: str, *, currency_hint: str | None = None) -> InvoiceData:
    lines = [ln.rstrip() for ln in text.replace("\f", "\n").splitlines()]
    decimal_comma = detect_decimal_comma(text)
    data = InvoiceData(method="rules")

    currency, cur_conf = detect_currency(text)
    if currency:
        data.set("currency", currency, cur_conf, currency)
    dayfirst = (currency or currency_hint) not in ("USD",)

    if inv := extract_invoice_number(lines):
        data.set("invoice_number", inv.value, inv.confidence, inv.evidence)
    if dt := extract_invoice_date(lines, dayfirst):
        cand, ambiguous = dt
        from datetime import date as _date

        data.set("invoice_date", _date.fromisoformat(cand.value), cand.confidence, cand.evidence)
        data.ambiguous_date = ambiguous
        if ambiguous:
            data.notes.append("invoice_date is ambiguous (day/month order inferred from locale)")
    customer = extract_customer(lines)
    if customer:
        data.set("customer_name", customer.value, customer.confidence, customer.evidence)
    if supplier := extract_supplier(lines, customer):
        data.set("supplier_name", supplier.value, supplier.confidence, supplier.evidence)

    for field, cand in extract_amounts(lines, decimal_comma).items():
        data.set(field, money(cand.value), cand.confidence, cand.evidence)

    data.line_items = extract_line_items(lines, decimal_comma)
    if data.line_items:
        data.confidence["line_items"] = 0.75
    return data


def page_signals(text: str) -> dict:
    """Cheap per-page signals used to split multi-invoice PDFs."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    inv = extract_invoice_number(lines[:40])
    marker = PAGE_MARKER.search(text)
    has_total = bool(_amount_after_label(lines, TOTAL_LABELS, NOT_TOTAL, detect_decimal_comma(text)))
    title = any(re.search(r"\b(tax\s+)?invoice\b|\breceipt\b", ln, re.I) for ln in lines[:12])
    return {
        "invoice_number": inv.value if inv else None,
        "page_of": (int(marker.group(1)), int(marker.group(2))) if marker else None,
        "has_total": has_total,
        "has_title": title,
        "chars": len(text.strip()),
    }
