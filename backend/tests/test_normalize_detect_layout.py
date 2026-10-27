from datetime import date
from decimal import Decimal

import pytest

from app.extraction.normalize import (
    detect_currency,
    find_amounts,
    find_dates,
    normalize_company,
    normalize_invoice_number,
    parse_amount,
    parse_date,
)
from app.pipeline.detect import detect_bytes
from app.pipeline.errors import CorruptedFile, EmptyDocument, UnsupportedFileType
from app.pipeline.layout import words_to_text


@pytest.mark.parametrize("raw,expected", [
    ("1,234.56", "1234.56"), ("1.234,56", "1234.56"), ("$1,234.56", "1234.56"), ("€ 99,90", "99.90"),
    ("USD 2,500", "2500"), ("(120.00)", "-120.00"), ("1'234.50", "1234.50"), ("12", "12"), ("0.5", "0.5"),
    ("Rs. 4,500.00", "4500.00"), ("1,234,567.89", "1234567.89"), ("-45.10", "-45.10"),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["abc", "", None, "12/03/2025", "1,23,4", "N/A"])
def test_parse_amount_rejects_non_numbers(raw):
    assert parse_amount(raw) is None


def test_parse_amount_three_decimals_uses_document_convention():
    assert parse_amount("1.234", decimal_comma=True) == Decimal("1234")
    assert parse_amount("1.234", decimal_comma=False) == Decimal("1.234")


def test_find_amounts_skips_percentages_dates_and_ids():
    text = "VAT 20%  on 14/03/2025  INV-2024  total 1,250.00"
    assert [a.value for a in find_amounts(text)] == [Decimal("1250.00")]


@pytest.mark.parametrize("text,dayfirst,expected,ambiguous", [
    ("2025-03-14", True, date(2025, 3, 14), False),
    ("14/03/2025", True, date(2025, 3, 14), False),
    ("03/14/2025", True, date(2025, 3, 14), False),  # unambiguous despite dayfirst
    ("03/04/2025", True, date(2025, 4, 3), True),
    ("03/04/2025", False, date(2025, 3, 4), True),
    ("14.03.2025", True, date(2025, 3, 14), False),
    ("March 14, 2025", True, date(2025, 3, 14), False),
    ("14 Mar 2025", True, date(2025, 3, 14), False),
    ("1st February 2025", True, date(2025, 2, 1), False),
])
def test_find_dates(text, dayfirst, expected, ambiguous):
    found = find_dates(text, dayfirst=dayfirst)
    assert found and found[0].value == expected and found[0].ambiguous == ambiguous


def test_parse_date_excel_serial_and_invalid():
    assert parse_date(45730) == date(2025, 3, 14)
    assert parse_date("31/02/2025") is None


def test_currency_detection():
    assert detect_currency("Total EUR 1.234,00")[0] == "EUR"
    assert detect_currency("Amount due £ 20.00")[0] == "GBP"
    code, conf = detect_currency("Total $ 20.00")
    assert code == "USD" and conf < 0.7  # bare dollar sign is weak evidence
    assert detect_currency("Total Rs. 2,000")[0] == "INR"
    assert detect_currency("no money here") == (None, 0.0)


def test_identifier_normalisation():
    assert normalize_invoice_number("inv-0001/a") == "INV0001A"
    assert normalize_company("ACME Industrial Supplies Ltd.") == normalize_company("Acme Industrial Supplies Limited")


@pytest.mark.parametrize("head,name,kind", [
    (b"%PDF-1.7\n...", "a.pdf", "pdf"), (b"\x89PNG\r\n\x1a\n....", "a.png", "image"),
    (b"\xff\xd8\xff\xe0....", "photo.jpeg", "image"), (b"II*\x00....", "scan.tif", "image"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1....", "old.xls", "xls"), (b"PK\x03\x04....", "book.xlsx", "xlsx"),
    (b"a,b,c\n1,2,3\n", "data.csv", "csv"), (b"%PDF-1.4", "renamed.png", "pdf"),
])
def test_detect_by_content(head, name, kind):
    assert detect_bytes(head, name).kind == kind


def test_detect_errors():
    with pytest.raises(EmptyDocument):
        detect_bytes(b"", "x.pdf")
    with pytest.raises(UnsupportedFileType):
        detect_bytes(b"hello", "notes.txt")
    with pytest.raises(CorruptedFile):
        detect_bytes(b"garbage bytes", "invoice.pdf")


def test_words_to_text_preserves_columns():
    words = [
        (10, 10, 60, 20, "Description"), (300, 10, 320, 20, "Qty"), (400, 10, 450, 20, "Amount"),
        (10, 30, 50, 40, "Steel"), (55, 30, 85, 40, "bolts"), (310, 30, 318, 40, "2"), (410, 30, 450, 40, "50.00"),
    ]
    lines = words_to_text(words).splitlines()
    assert lines[0].split() == ["Description", "Qty", "Amount"]
    assert "Steel bolts" in lines[1]  # same phrase: single space
    assert "  2  " in lines[1] or lines[1].split("  ")[-1].strip() == "50.00"
