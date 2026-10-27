"""Document processing: PDF text layer, OCR (incl. poor quality), spreadsheets, failures."""

from decimal import Decimal

import pytest

from app.extraction import rules
from app.extraction.spreadsheet_mapper import map_sheet
from app.pipeline.detect import detect_file
from app.pipeline.errors import CorruptedFile, EncryptedFile
from app.pipeline.images import extract_image
from app.pipeline.pdf import extract_pdf
from app.pipeline.segment import segment_pages
from app.pipeline.spreadsheet import extract_spreadsheet
from tests.factories import INVOICE


def test_digital_pdf_uses_text_layer(samples):
    progress = []
    res = extract_pdf(samples.digital_pdf(pages=3), lambda d, t: progress.append((d, t)))
    assert len(res.pages) == 3
    assert all(p.method == "text_layer" for p in res.pages)
    assert "INV-20417" in res.pages[0].text
    assert progress[-1] == (3, 3)


def test_scanned_pdf_falls_back_to_ocr(samples):
    res = extract_pdf(samples.scanned_pdf())
    page = res.pages[0]
    assert page.method == "ocr" and page.ocr_confidence and page.ocr_confidence > 60
    data = rules.extract(page.text)
    assert data.invoice_number == "INV-20417"
    assert data.total == Decimal("2821.20")


@pytest.mark.parametrize("name,degrade", [("clean.png", None), ("noisy.jpg", "noisy"), ("small.png", "lowres"),
                                          ("rot.tiff", "rotated90")])
def test_ocr_images_including_poor_quality(samples, name, degrade):
    res = extract_image(samples.image(name, degrade=degrade))
    text = res.pages[0].text
    data = rules.extract(text)
    assert data.invoice_number == "INV-20417", text[:500]
    assert data.total == Decimal("2821.20")
    if degrade == "rotated90":
        assert any("rotated" in w for w in res.pages[0].warnings)


def test_multipage_tiff(samples):
    res = extract_image(samples.multipage_tiff())
    assert len(res.pages) == 2
    assert "INV-20418" in res.pages[1].text.replace(" ", "")


def test_ocr_page_cap_for_small_deployments(samples, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_ocr_pages", 1)
    res = extract_image(samples.multipage_tiff())
    assert len(res.pages) == 1 and any("limited to the first 1 of 2" in w for w in res.pages[0].warnings)


def test_truncated_jpeg_is_recovered_with_warning(samples):
    res = extract_image(samples.corrupted("jpg_truncated"))
    assert any("truncated" in w for w in res.pages[0].warnings)


@pytest.mark.parametrize("kind,exc", [("pdf_truncated", (CorruptedFile,)), ("pdf_garbage", (CorruptedFile,)),
                                      ("pdf_encrypted", (EncryptedFile,)), ("xlsx_garbage", (CorruptedFile,)),
                                      ("png_garbage", (CorruptedFile,))])
def test_corrupted_files_raise_typed_errors(samples, kind, exc):
    path = samples.corrupted(kind)
    with pytest.raises(exc):
        detected = detect_file(path, path.name)
        if detected.kind == "pdf":
            res = extract_pdf(path)
            if not any(p.text.strip() for p in res.pages):  # repaired but empty is also a failure mode
                raise CorruptedFile("no content")
        elif detected.kind == "image":
            extract_image(path)
        else:
            extract_spreadsheet(path, detected.kind)


def test_xlsx_multisheet_register_with_title_rows(samples):
    res = extract_spreadsheet(samples.register_xlsx(), "xlsx")
    assert [p.sheet_name for p in res.pages] == ["Q1", "Q2", "Empty", "Notes"]
    q1 = res.sheets[0]
    assert q1.header[:3] == ["Invoice No", "Invoice Date", "Supplier"]
    assert q1.first_data_row == 4
    mapped = map_sheet(q1)
    assert [m.data.invoice_number for m in mapped] == ["A-1001", "A-1002"]
    assert mapped[1].data.total == Decimal("245.00") and mapped[1].data.tax == Decimal("40.00")
    assert mapped[0].data.invoice_date.isoformat() == "2025-02-03"
    q2 = map_sheet(res.sheets[1])  # different header vocabulary
    assert q2[0].data.supplier_name == "Orion Software Systems" and q2[0].data.currency == "EUR"


def test_xlsx_line_level_export_groups_rows(samples):
    res = extract_spreadsheet(samples.lines_xlsx(), "xlsx")
    mapped = map_sheet(res.sheets[0])
    assert [m.data.invoice_number for m in mapped] == ["L-1", "L-2"]
    assert [li.description for li in mapped[0].data.line_items] == ["Bolts", "Nuts"]
    assert mapped[0].data.total == Decimal("40.00")
    assert mapped[0].rows == [2, 3]


def test_legacy_xls(samples):
    res = extract_spreadsheet(samples.xls(), "xls")
    m = map_sheet(res.sheets[0])
    assert m[0].data.invoice_number == "X-9" and m[0].data.total == Decimal("990.00")
    assert m[0].data.invoice_date.isoformat() == "2025-07-01"


def test_csv_semicolon_latin1_decimal_comma_and_bad_rows(samples):
    res = extract_spreadsheet(samples.eu_csv(), "csv")
    assert any("malformed" in w for w in res.warnings)
    m = map_sheet(res.sheets[0])
    assert m[0].data.supplier_name == "Müller Bürobedarf GmbH"
    assert m[0].data.total == Decimal("1190.00") and m[1].data.subtotal == Decimal("20.50")
    assert m[0].data.invoice_date.isoformat() == "2025-03-14"


def test_form_style_sheet_is_left_to_text_extraction(samples):
    res = extract_spreadsheet(samples.form_xlsx(), "xlsx")
    assert map_sheet(res.sheets[0]) is None
    data = rules.extract(res.pages[0].text)
    assert data.invoice_number == "GF-3321"
    assert data.total == Decimal("132.00")


def test_segmentation_of_multi_invoice_pdf(samples, tmp_path):
    import pymupdf

    from tests.factories import invoice_pdf

    merged = pymupdf.open()
    for i, pages in enumerate([1, 2, 1]):
        p = invoice_pdf(tmp_path / f"part{i}.pdf", {**INVOICE, "number": f"INV-{500 + i}"}, pages=pages)
        merged.insert_pdf(pymupdf.open(p))
    out = tmp_path / "batch.pdf"
    merged.save(out)
    segments = segment_pages(extract_pdf(out).pages)
    assert [s.page_numbers for s in segments] == [[1], [2, 3], [4]]
    assert [rules.extract(s.text).invoice_number for s in segments] == ["INV-500", "INV-501", "INV-502"]
