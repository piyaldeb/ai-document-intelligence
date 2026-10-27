"""Locale-aware parsing of amounts, dates, currencies and identifiers.

Everything here is deterministic and conservative: when a value cannot be parsed
unambiguously we return None (or flag the ambiguity) instead of guessing.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from dateutil import parser as dateparser

CURRENCY_CODES = {
    "USD", "EUR", "GBP", "INR", "BDT", "JPY", "CNY", "CAD", "AUD", "CHF", "SGD", "AED", "SAR",
    "HKD", "NZD", "SEK", "NOK", "DKK", "ZAR", "MYR", "THB", "PKR", "LKR", "KRW", "BRL", "MXN",
    "PLN", "CZK", "TRY", "IDR", "PHP", "VND", "QAR", "KWD", "EGP", "NGN", "KES", "RUB",
}
SYMBOLS = {"€": "EUR", "£": "GBP", "₹": "INR", "৳": "BDT", "¥": "JPY", "₩": "KRW", "₺": "TRY", "₱": "PHP"}
DOLLAR_PREFIXES = {"US$": "USD", "C$": "CAD", "CA$": "CAD", "A$": "AUD", "AU$": "AUD", "S$": "SGD",
                   "NZ$": "NZD", "HK$": "HKD"}
LOCAL_WORDS = {r"\bRs\.?(?=\s?\d)": "INR", r"\bTk\.?(?=\s?\d)": "BDT"}

# Number token: optional sign/paren, optional currency symbol, digits with , . ' separators.
_AMOUNT_TOKEN = re.compile(
    r"(?<![\w.,/-])"
    r"(\(?-?\s?(?:[$€£₹৳¥]\s?)?\d{1,3}(?:[,.']\d{3})*(?:[.,]\d{1,4})?\)?|\(?-?\s?(?:[$€£₹৳¥]\s?)?\d+(?:[.,]\d{1,4})?\)?)"
    r"(?![\w/-]|[.,]\d)(?!\s?%)"
)
_CODE_STRIP = re.compile(r"\b(" + "|".join(sorted(CURRENCY_CODES)) + r")\b", re.I)

MONEY_Q = Decimal("0.01")


def money(value: Decimal | float | int | str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def detect_decimal_comma(text: str) -> bool:
    """Document-level number convention: True if amounts look like 1.234,56."""
    comma = len(re.findall(r"\d,\d{2}(?!\d)", text))
    dot = len(re.findall(r"\d\.\d{2}(?!\d)", text))
    return comma > dot


def parse_amount(raw: object, decimal_comma: bool | None = None) -> Decimal | None:
    """Parse a monetary / numeric string. Returns None if it is not a clean number."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float, Decimal)):
        try:
            d = Decimal(str(raw))
        except InvalidOperation:
            return None
        return None if d.is_nan() else d
    s = str(raw).strip()
    if not s:
        return None
    s = unicodedata.normalize("NFKC", s)
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()
    for prefix in DOLLAR_PREFIXES:
        s = s.replace(prefix, "")
    s = _CODE_STRIP.sub("", s)
    s = re.sub(r"[$€£₹৳¥₩₺₱]|\bRs\.?|\bTk\.?", "", s, flags=re.I).strip()
    if s.startswith("-"):
        negative, s = True, s[1:].strip()
    if s.endswith("-"):
        negative, s = True, s[:-1].strip()
    s = s.replace("'", "").replace(" ", "").replace(" ", "")
    if not s or not re.fullmatch(r"[\d.,]+", s) or not re.search(r"\d", s):
        return None

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            s = s.replace(",", ".")
        elif len(parts) == 2 and len(parts[1]) == 3 and decimal_comma:
            s = s.replace(",", ".")
        elif all(len(p) == 3 for p in parts[1:]):
            s = s.replace(",", "")
        else:
            return None
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2:
            if all(len(p) == 3 for p in parts[1:]):
                s = s.replace(".", "")
            else:
                return None
        elif len(parts[1]) == 3 and decimal_comma:
            s = s.replace(".", "")  # 1.234 in a 1.234,56 document = one thousand two hundred ...
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return -d if negative else d


@dataclass
class AmountMatch:
    value: Decimal
    raw: str
    start: int
    end: int


_GLUED_PREFIX = re.compile(r"(\bRs\.|\bTk\.?|\b(?:" + "|".join(sorted(CURRENCY_CODES)) + r"))(?=\d)")


def find_amounts(text: str, decimal_comma: bool | None = None) -> list[AmountMatch]:
    # "Rs.9,754.28" / "USD1,200.00": separate the prefix so the number is a token of its own.
    text = _GLUED_PREFIX.sub(r"\1 ", text)
    out = []
    for m in _AMOUNT_TOKEN.finditer(text):
        raw = m.group(1).strip()
        val = parse_amount(raw, decimal_comma)
        if val is not None:
            out.append(AmountMatch(val, raw, m.start(1), m.end(1)))
    return out


# ---------------------------------------------------------------- dates

_MONTHS = r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
DATE_PATTERNS = [
    re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"),  # ISO-like
    re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})\b"),  # numeric d/m/y or m/d/y
    re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s\-/]+({_MONTHS})\.?[\s\-/,]+(\d{{4}})\b", re.I),
    re.compile(rf"\b({_MONTHS})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I),
]


@dataclass
class DateMatch:
    value: date
    raw: str
    start: int
    ambiguous: bool


def _valid(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def find_dates(text: str, dayfirst: bool = True) -> list[DateMatch]:
    found: list[DateMatch] = []
    taken: list[tuple[int, int]] = []
    for idx, pat in enumerate(DATE_PATTERNS):
        for m in pat.finditer(text):
            if any(a <= m.start() < b for a, b in taken):
                continue
            raw = m.group(0)
            ambiguous = False
            value: date | None = None
            if idx == 0:
                value = _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            elif idx == 1:
                a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
                year = int(y) + (2000 if len(y) == 2 and int(y) < 70 else 1900 if len(y) == 2 else 0)
                if a > 12 and b <= 12:
                    value = _valid(year, b, a)
                elif b > 12 and a <= 12:
                    value = _valid(year, a, b)
                elif a <= 12 and b <= 12:
                    ambiguous = a != b
                    value = _valid(year, b, a) if dayfirst else _valid(year, a, b)
            else:
                try:
                    value = dateparser.parse(raw, dayfirst=True, fuzzy=False).date()
                except (ValueError, OverflowError):
                    value = None
            if value is not None:
                found.append(DateMatch(value, raw, m.start(), ambiguous))
                taken.append((m.start(), m.end()))
    found.sort(key=lambda d: d.start)
    return found


def parse_date(raw: object, dayfirst: bool = True) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, (int, float)) and 20000 < float(raw) < 80000:
        # Excel serial date (1900 system).
        from datetime import timedelta

        return date(1899, 12, 30) + timedelta(days=int(raw))
    s = str(raw).strip()
    if not s:
        return None
    matches = find_dates(s, dayfirst=dayfirst)
    if matches:
        return matches[0].value
    try:
        return dateparser.parse(s, dayfirst=dayfirst).date()
    except (ValueError, OverflowError, TypeError):
        return None


# ---------------------------------------------------------------- currency


def detect_currency(text: str) -> tuple[str | None, float]:
    """Return (ISO code, confidence). Explicit ISO codes beat symbols; bare '$' is weak."""
    counts: dict[str, int] = {}
    for m in re.finditer(r"\b([A-Z]{3})\b", text):
        code = m.group(1)
        if code in CURRENCY_CODES:
            counts[code] = counts.get(code, 0) + 2
    for prefix, code in DOLLAR_PREFIXES.items():
        n = text.count(prefix)
        if n:
            counts[code] = counts.get(code, 0) + 2 * n
    for sym, code in SYMBOLS.items():
        n = text.count(sym)
        if n:
            counts[code] = counts.get(code, 0) + n
    for pat, code in LOCAL_WORDS.items():
        n = len(re.findall(pat, text))
        if n:
            counts[code] = counts.get(code, 0) + n
    if counts:
        code = max(counts, key=counts.get)
        return code, 0.95 if counts[code] >= 2 else 0.8
    if "$" in text:
        return "USD", 0.6
    return None, 0.0


def normalize_currency(raw: object) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if s.upper() in CURRENCY_CODES:
        return s.upper()
    code, conf = detect_currency(s)
    return code if conf >= 0.6 else None


# ---------------------------------------------------------------- identifiers

_COMPANY_SUFFIXES = re.compile(
    r"\b(ltd|limited|inc|incorporated|llc|l\.l\.c|gmbh|corp|corporation|co|company|plc|pvt|private|"
    r"sa|s\.a|bv|b\.v|ag|pte|pty|llp|srl|oy|ab)\b\.?",
    re.I,
)


def normalize_invoice_number(raw: str | None) -> str | None:
    if not raw:
        return None
    s = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    return s or None


def normalize_company(raw: str | None) -> str | None:
    if not raw:
        return None
    s = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    s = _COMPANY_SUFFIXES.sub(" ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def normalize_text_for_match(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)
