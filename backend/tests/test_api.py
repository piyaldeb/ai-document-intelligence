"""REST API end-to-end tests (upload -> background pipeline -> results -> correction -> search)."""

from pathlib import Path

from tests.factories import INVOICE, invoice_pdf


def upload(client, *paths: Path):
    files = [("files", (p.name, p.read_bytes())) for p in paths]
    r = client.post("/api/documents", files=files)
    assert r.status_code == 202, r.text
    return r.json()


def test_auth_required(client):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as anon:
        assert anon.get("/api/documents").status_code == 401
        assert anon.get("/api/documents", headers={"X-API-Key": "wrong"}).status_code == 401
        assert anon.get("/api/health").status_code == 200


def test_upload_multiple_and_reject_unsupported(client, samples, tmp_path):
    txt = tmp_path / "notes.txt"
    txt.write_text("hello")
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    res = upload(client, samples.digital_pdf(), samples.register_xlsx(), txt, empty)
    assert res["accepted"] == 2 and res["rejected"] == 2
    rejected = {r["filename"]: r["error"] for r in res["results"] if not r["accepted"]}
    assert "Unsupported" in rejected["notes.txt"] and "empty" in rejected["empty.png"].lower()

    docs = client.get("/api/documents").json()
    assert docs["meta"]["total"] == 2
    by_type = {d["file_type"]: d for d in docs["items"]}
    assert by_type["pdf"]["status"] == "completed" and by_type["pdf"]["progress"] == 100
    assert by_type["xlsx"]["invoice_count"] == 3


def test_document_detail_status_pages_history_and_file(client, samples):
    doc_id = upload(client, samples.digital_pdf(pages=2))["results"][0]["document_id"]
    status = client.get(f"/api/documents/{doc_id}/status").json()
    assert status["status"] in ("completed", "needs_review") and status["invoice_count"] == 1
    detail = client.get(f"/api/documents/{doc_id}").json()
    assert detail["page_count"] == 2 and len(detail["pages"]) == 2 and "text" not in detail["pages"][0]
    stages = [(e["stage"], e["status"]) for e in detail["events"]]
    for stage in ("detect", "extract_text", "segment", "ai_extraction", "validate", "index"):
        assert (stage, "completed") in stages
    pages = client.get(f"/api/documents/{doc_id}/pages").json()
    assert "INV-20417" in pages[0]["text"]
    f = client.get(f"/api/documents/{doc_id}/file")
    assert f.status_code == 200 and f.content.startswith(b"%PDF")


def test_extracted_invoice_json(client, samples):
    upload(client, samples.digital_pdf())
    inv = client.get("/api/invoices").json()["items"][0]
    detail = client.get(f"/api/invoices/{inv['id']}").json()
    assert detail["invoice_number"] == "INV-20417"
    assert detail["invoice_date"] == "2025-03-14"
    assert detail["supplier_name"] == "Acme Industrial Supplies Ltd"
    assert detail["customer_name"] == "Riverside Home Care"
    assert (detail["subtotal"], detail["tax"], detail["total"]) == (2351.0, 470.2, 2821.2)
    assert detail["currency"] == "GBP"
    assert len(detail["line_items"]) == 2 and detail["line_items"][0]["amount"] == 1500.0
    assert detail["field_confidence"]["invoice_number"] > 0.8
    assert detail["review_status"] == "ok"


def test_validation_errors_correction_audit_and_approval(client, samples, tmp_path):
    bad = invoice_pdf(tmp_path / "bad_total.pdf", {**INVOICE, "total": "2,900.00"})
    upload(client, bad)
    inv = client.get("/api/invoices", params={"review_status": "needs_review"}).json()["items"][0]
    detail = client.get(f"/api/invoices/{inv['id']}").json()
    assert "TOTAL_MISMATCH" in {i["code"] for i in detail["issues"]}
    assert client.post(f"/api/invoices/{inv['id']}/approve", json={}).status_code == 409

    r = client.patch(f"/api/invoices/{inv['id']}", json={"total": "2821.20", "reason": "typo on scan",
                                                          "corrected_by": "reviewer@example.com"})
    assert r.status_code == 200, r.text
    fixed = r.json()
    assert fixed["total"] == 2821.2 and fixed["review_status"] == "ok" and fixed["error_count"] == 0
    assert fixed["corrections"][0]["field"] == "total" and fixed["corrections"][0]["old_value"] == "2900.00"
    assert fixed["field_confidence"]["total"] == 1.0

    approved = client.post(f"/api/invoices/{inv['id']}/approve", json={"approved_by": "lead"}).json()
    assert approved["review_status"] == "approved"
    doc = client.get(f"/api/documents/{inv['document_id']}").json()
    assert doc["status"] == "completed"


def test_correction_rejects_unknown_fields_and_bad_values(client, samples):
    upload(client, samples.digital_pdf())
    inv_id = client.get("/api/invoices").json()["items"][0]["id"]
    assert client.patch(f"/api/invoices/{inv_id}", json={"is_admin": True}).status_code == 422
    assert client.patch(f"/api/invoices/{inv_id}", json={"currency": "DOLLARS"}).status_code == 422
    assert client.patch(f"/api/invoices/{inv_id}", json={}).status_code == 422


def test_line_item_correction_revalidates(client, samples):
    upload(client, samples.digital_pdf())
    inv_id = client.get("/api/invoices").json()["items"][0]["id"]
    r = client.patch(f"/api/invoices/{inv_id}", json={"line_items": [
        {"description": "Consulting services", "quantity": "10", "unit_price": "150", "amount": "1500"}]})
    codes = {i["code"] for i in r.json()["issues"]}
    assert "LINE_ITEMS_MISMATCH" in codes and r.json()["review_status"] == "needs_review"


def test_duplicate_invoice_across_documents(client, samples, tmp_path):
    upload(client, samples.digital_pdf("first.pdf"))
    upload(client, samples.image("again.png"))  # same invoice, scanned
    items = client.get("/api/invoices", params={"sort": "created_desc"}).json()["items"]
    later = client.get(f"/api/invoices/{items[0]['id']}").json()
    assert "DUPLICATE_INVOICE" in {i["code"] for i in later["issues"]}
    assert client.get("/api/invoices", params={"issue_code": "DUPLICATE_INVOICE"}).json()["meta"]["total"] == 1


def test_duplicate_file_upload_is_flagged(client, samples):
    p = samples.digital_pdf()
    first = upload(client, p)["results"][0]
    second = upload(client, p)["results"][0]
    assert second["duplicate_of"] == first["document_id"]
    doc = client.get(f"/api/documents/{second['document_id']}").json()
    assert "DUPLICATE_FILE" in {i["code"] for i in doc["issues"]}
    assert doc["status"] == "needs_review"


def test_invoice_filters(client, samples):
    upload(client, samples.register_xlsx(), samples.digital_pdf())
    get = lambda **p: client.get("/api/invoices", params=p).json()["meta"]["total"]  # noqa: E731
    assert get() == 4
    assert get(currency="USD") == 2
    assert get(supplier="bluewave") == 1
    assert get(min_total=200, max_total=300) == 1
    assert get(date_from="2025-05-01") == 1
    assert get(q="Orion") == 1
    assert get(invoice_number="A-100") == 2
    assert get(file_type="pdf") == 1
    totals = [i["total"] for i in client.get("/api/invoices", params={"sort": "total_desc"}).json()["items"]]
    assert totals == sorted(totals, reverse=True)


def test_keyword_semantic_and_hybrid_search(client, samples):
    upload(client, samples.digital_pdf(), samples.register_xlsx())
    kw = client.get("/api/search", params={"q": "INV-20417", "mode": "keyword"}).json()
    assert kw["results"] and kw["results"][0]["invoice"]["invoice_number"] == "INV-20417"
    text_hit = client.get("/api/search", params={"q": "consulting", "mode": "keyword"}).json()["results"]
    assert any("<<" in h["snippet"] for h in text_hit)
    sem = client.get("/api/search", params={"q": "software licence renewal", "mode": "semantic"}).json()
    assert "invoice.pdf" in [h["document_name"] for h in sem["results"][:3]]
    hyb = client.get("/api/search", params={"q": "Northwind", "mode": "hybrid", "currency": "USD"}).json()
    assert hyb["results"][0]["invoice"]["supplier_name"] == "Northwind Traders Inc"


def test_pdf_vs_excel_cross_verification(client, samples, tmp_path):
    import openpyxl

    pdf_id = upload(client, samples.digital_pdf())["results"][0]["document_id"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Invoice No", "Invoice Date", "Supplier", "Customer", "Subtotal", "Tax", "Total", "Currency"])
    ws.append(["INV-20417", "2025-03-14", "Acme Industrial Supplies Limited", "Riverside Home Care", 2351, 470.2, 2900, "GBP"])
    ws.append(["INV-1", "2025-03-15", "Other Co", "X", 1, 0, 1, "GBP"])
    xlsx = tmp_path / "erp.xlsx"
    wb.save(xlsx)
    xlsx_id = upload(client, xlsx)["results"][0]["document_id"]
    rec = client.post("/api/reconciliations", json={"left_document_id": pdf_id, "right_document_id": xlsx_id}).json()
    assert rec["summary"]["mismatch"] == 1 and rec["summary"]["missing_in_left"] == 1
    mismatch = next(i for i in rec["items"] if i["status"] == "mismatch")
    assert [d["field"] for d in mismatch["differences"]] == ["total"]  # supplier "Ltd" vs "Limited" still matches
    assert client.get(f"/api/reconciliations/{rec['id']}").json()["id"] == rec["id"]
    assert client.post("/api/reconciliations", json={"left_document_id": pdf_id,
                                                     "right_document_id": pdf_id}).status_code == 422


def test_failed_job_and_reprocessing(client, samples, monkeypatch):
    doc_id = upload(client, samples.corrupted("pdf_garbage"))["results"][0]["document_id"]
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert doc["status"] == "failed" and doc["error_code"] == "CORRUPTED_FILE"
    assert client.get("/api/jobs", params={"status": "failed"}).json()["meta"]["total"] == 1

    # Simulate the file being fixed on storage, then reprocess the failed job.
    from app.db import SessionLocal
    from app.models import Document

    with SessionLocal() as db:
        d = db.get(Document, doc_id)
        Path(d.storage_path).write_bytes(samples.digital_pdf("fixed.pdf").read_bytes())
    r = client.post(f"/api/documents/{doc_id}/reprocess")
    assert r.status_code == 202
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert doc["status"] == "completed" and doc["attempts"] == 2 and doc["error_code"] is None
    assert {e["attempt"] for e in doc["events"]} == {1, 2}


def test_retry_all_failed_and_delete(client, samples):
    upload(client, samples.corrupted("pdf_encrypted"), samples.corrupted("xlsx_garbage"))
    failed = client.get("/api/jobs").json()
    codes = {d["error_code"] for d in failed["items"]}
    assert codes == {"ENCRYPTED_FILE", "CORRUPTED_FILE"}
    assert len(client.post("/api/jobs/retry-failed").json()["queued"]) == 2
    doc_id = failed["items"][0]["id"]
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert client.get(f"/api/documents/{doc_id}").status_code == 404


def test_unexpected_errors_are_contained(client, samples, monkeypatch):
    import app.pipeline.processor as processor

    def explode(*a, **k):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(processor, "segment_pages", explode)
    doc_id = upload(client, samples.digital_pdf())["results"][0]["document_id"]
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert doc["status"] == "failed" and doc["error_code"] == "INTERNAL_ERROR"
    assert "secret" not in doc["error_message"]


def test_stats(client, samples):
    upload(client, samples.digital_pdf(), samples.corrupted("pdf_garbage"))
    s = client.get("/api/stats").json()
    assert s["documents"]["total"] == 2 and s["documents"]["failed"] == 1
    assert s["invoices"]["total"] == 1 and s["extraction_provider"] == "rules"
    assert s["total_amount_by_currency"]["GBP"] == 2821.2


def test_public_demo_caps_stored_documents(client, samples, monkeypatch):
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "demo_mode", True)
    monkeypatch.setattr(s, "demo_max_documents", 1)
    upload(client, samples.digital_pdf())
    r = client.post("/api/documents", files=[("files", ("x.pdf", samples.digital_pdf("x.pdf").read_bytes()))])
    assert r.status_code == 429 and "resets" in r.json()["detail"]
    assert client.get("/api/health").json()["demo_mode"] is True


def test_serverless_mode_db_storage_inline_and_demo_reset(client, samples, monkeypatch, tmp_path):
    import shutil

    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import Document

    s = get_settings()
    monkeypatch.setattr(s, "storage_backend", "db")
    monkeypatch.setattr(s, "processing_mode", "inline")
    doc_id = upload(client, samples.digital_pdf())["results"][0]["document_id"]
    # Another serverless instance has no local copy: the original must come from Postgres.
    with SessionLocal() as db:
        Path(db.get(Document, doc_id).storage_path).unlink()
    r = client.get(f"/api/documents/{doc_id}/file")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    r = client.post(f"/api/documents/{doc_id}/reprocess")  # processing also re-materializes the file
    assert client.get(f"/api/documents/{doc_id}").json()["status"] in ("completed", "needs_review")

    demo_dir = tmp_path / "demo"
    (demo_dir / "pdf").mkdir(parents=True)
    shutil.copy(samples.digital_pdf("seed.pdf"), demo_dir / "pdf" / "classic_01.pdf")
    monkeypatch.setattr(s, "demo_samples_dir", demo_dir)
    monkeypatch.setattr(s, "demo_mode", True)
    monkeypatch.setattr(s, "cron_secret", "s3cret")
    assert client.post("/api/admin/demo-reset").status_code == 401
    assert client.post("/api/admin/demo-reset", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = client.post("/api/admin/demo-reset", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200 and r.json()["documents"] == 1
    docs = client.get("/api/documents").json()
    assert docs["meta"]["total"] == 1 and docs["items"][0]["original_filename"] == "classic_01.pdf"
