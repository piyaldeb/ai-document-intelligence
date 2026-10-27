from datetime import date, timedelta
from decimal import Decimal as D

from app.validation.rules import DuplicateContext, InvoiceView, needs_review, validate


def view(**kw) -> InvoiceView:
    base = dict(
        invoice_number="INV-1", invoice_date=date(2025, 3, 14), supplier_name="Acme Ltd", customer_name="Foo",
        subtotal=D("100.00"), tax=D("20.00"), total=D("120.00"), currency="USD",
        line_items=[{"quantity": D("2"), "unit_price": D("50.00"), "amount": D("100.00")}],
    )
    base.update(kw)
    return InvoiceView(**base)


def codes(issues, severity=None):
    return {i.code for i in issues if severity is None or i.severity == severity}


def test_clean_invoice_passes():
    issues = validate(view(), today=date(2025, 6, 1))
    assert not needs_review(issues)
    assert codes(issues, "error") == set() and codes(issues, "warning") == set()


def test_missing_required_fields_are_errors():
    issues = validate(view(invoice_number=None, total=None, supplier_name=""), today=date(2025, 6, 1))
    missing = {i.field for i in issues if i.code == "MISSING_FIELD" and i.severity == "error"}
    assert missing == {"invoice_number", "total", "supplier_name"}
    assert needs_review(issues)


def test_missing_optional_fields_are_informational_except_currency():
    issues = validate(view(customer_name=None, currency=None, tax=None, subtotal=None, total=D("100.00")),
                      today=date(2025, 6, 1))
    sev = {i.field: i.severity for i in issues if i.code == "MISSING_FIELD"}
    assert sev == {"customer_name": "info", "currency": "warning", "subtotal": "info", "tax": "info"}


def test_total_mismatch():
    issues = validate(view(total=D("130.00")), today=date(2025, 6, 1))
    mismatch = [i for i in issues if i.code == "TOTAL_MISMATCH"]
    assert mismatch and mismatch[0].details["difference"] == "10.00"


def test_rounding_within_tolerance_is_accepted():
    assert "TOTAL_MISMATCH" not in codes(validate(view(total=D("120.01")), today=date(2025, 6, 1)))


def test_line_items_sum_and_line_math():
    items = [{"quantity": D("2"), "unit_price": D("50.00"), "amount": D("100.00")},
             {"quantity": D("1"), "unit_price": D("10.00"), "amount": D("12.00")}]
    c = codes(validate(view(line_items=items), today=date(2025, 6, 1)))
    assert {"LINE_ITEMS_MISMATCH", "LINE_ITEM_MATH"} <= c


def test_numeric_sanity_rules():
    c = codes(validate(view(subtotal=D("100"), tax=D("60"), total=D("160")), today=date(2025, 6, 1)))
    assert "UNUSUAL_TAX_RATE" in c
    c = codes(validate(view(subtotal=D("200"), tax=D("0"), total=D("150"),
                            line_items=[]), today=date(2025, 6, 1)))
    assert "SUBTOTAL_EXCEEDS_TOTAL" in c
    c = codes(validate(view(total=D("-5"), subtotal=None, tax=None, line_items=[]), today=date(2025, 6, 1)))
    assert "NEGATIVE_AMOUNT" in c
    c = codes(validate(view(total=None, subtotal=None, tax=None, line_items=[], rejected={"total": "12,3,4"}),
                       today=date(2025, 6, 1)))
    assert "INVALID_NUMBER" in c


def test_date_rules():
    today = date(2025, 6, 1)
    assert "FUTURE_DATE" in codes(validate(view(invoice_date=today + timedelta(days=30)), today=today))
    assert "OLD_DATE" in codes(validate(view(invoice_date=date(2010, 1, 1)), today=today))
    assert "AMBIGUOUS_DATE" in codes(validate(view(ambiguous_date=True), today=today))
    assert "INVALID_DATE" in codes(validate(view(invoice_date=None, rejected={"invoice_date": "31/02/2025"}), today=today))


def test_duplicates_and_quality_flags():
    dup = DuplicateContext(exact=[{"invoice_id": "x", "document_name": "a.pdf"}],
                           probable=[{"invoice_id": "y", "invoice_number": "INV-2"}])
    issues = validate(view(confidence={"total": 0.4}, min_ocr_confidence=41.0,
                           rejected={"supplier_name": "Hallucinated Corp"}), dup, today=date(2025, 6, 1))
    c = codes(issues)
    assert {"DUPLICATE_INVOICE", "POSSIBLE_DUPLICATE", "LOW_CONFIDENCE", "LOW_OCR_QUALITY"} <= c
    assert any(i.code == "DUPLICATE_INVOICE" and i.severity == "error" for i in issues)


def test_unknown_currency():
    assert "UNKNOWN_CURRENCY" in codes(validate(view(currency="XYZ"), today=date(2025, 6, 1)))
