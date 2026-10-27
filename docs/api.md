# REST API

Base URL `http://localhost:8000`. Every endpoint except `/api/health` requires the header `X-API-Key: <API_KEY>`. The interactive OpenAPI docs are at `/docs` and the machine-readable spec at `/openapi.json`. Errors use FastAPI's shape `{"detail": ...}`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/documents` | **Upload** one or more files (`multipart/form-data`, field `files`, repeatable). Returns `202` with a per-file result (`accepted`, `document_id`, `duplicate_of`, or `error`). Processing runs in the background. |
| `GET` | `/api/documents` | List documents: `status` (comma list), `file_type`, `q` (filename), `ids` (comma list, for progress polling), `page`, `page_size` |
| `GET` | `/api/documents/{id}` | Document detail: metadata, status, progress, page metadata, invoices, **processing history** (events) and document-level issues |
| `GET` | `/api/documents/{id}/status` | Lightweight **processing status** (status, stage, progress, error) |
| `GET` | `/api/documents/{id}/pages?page_from&page_to` | **Extracted text** per page or sheet, with method (`text_layer`/`ocr`/`spreadsheet`), OCR confidence and warnings |
| `GET` | `/api/documents/{id}/file` | Original file (inline for PDF and images) |
| `POST` | `/api/documents/{id}/reprocess` | **Reprocess** a document (e.g. a failed job); idempotent |
| `DELETE` | `/api/documents/{id}` | Delete a document and everything derived from it |
| `GET` | `/api/jobs?status=failed` | Failed (or other-status) jobs |
| `POST` | `/api/jobs/retry-failed` | **Re-queue all failed jobs** |
| `GET` | `/api/invoices` | **Extracted results** with keyword filtering: `q`, `supplier`, `customer`, `invoice_number`, `currency`, `date_from`, `date_to`, `min_total`, `max_total`, `review_status` (`ok`/`needs_review`/`approved`), `issue_code`, `file_type`, `document_id`, `sort`, `page`, `page_size` |
| `GET` | `/api/invoices/{id}` | Invoice JSON: fields, line items, per-field confidence, evidence, rejected (ungrounded) values, validation issues, correction history, source text |
| `PATCH` | `/api/invoices/{id}` | **Manual correction**: send only the changed fields (and/or `line_items` to replace them), plus `reason` and `corrected_by`. Each change is audited and the invoice is re-validated. |
| `POST` | `/api/invoices/{id}/approve` | Mark as reviewed. Returns `409` while errors remain unless `{"force": true}`. |
| `GET` | `/api/search?q&mode` | **Document search**: `mode=keyword` (Postgres full-text + fuzzy fields), `semantic` (pgvector), `hybrid` (reciprocal rank fusion, default). Accepts the invoice filters above. |
| `POST` | `/api/reconciliations` | **Cross-verify** two processed documents `{left_document_id, right_document_id, amount_tolerance}` |
| `GET` | `/api/reconciliations[/{id}]` | Previous cross-verifications |
| `GET` | `/api/stats` | Dashboard counters |
| `GET` | `/api/health` | Liveness (and DB connectivity) |

## Example

```bash
KEY=$(grep ^API_KEY= .env | cut -d= -f2)

# upload three files at once
curl -s -H "X-API-Key: $KEY" \
  -F files=@eval/dataset/pdf/classic_01.pdf \
  -F files=@eval/dataset/images/modern_scan_03.jpg \
  -F files=@eval/dataset/spreadsheets/legacy_register.xls \
  http://localhost:8000/api/documents

# poll status
curl -s -H "X-API-Key: $KEY" http://localhost:8000/api/documents/<id>/status
# -> {"id":"…","status":"processing","stage":"extract_text","progress":34,…}

# invoices that need review, largest first
curl -s -H "X-API-Key: $KEY" "http://localhost:8000/api/invoices?review_status=needs_review&sort=total_desc"

# correct a value (audited + re-validated)
curl -s -X PATCH -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"total": "2821.20", "reason": "OCR misread", "corrected_by": "ap.clerk"}' \
  http://localhost:8000/api/invoices/<invoice-id>

# semantic search
curl -s -H "X-API-Key: $KEY" "http://localhost:8000/api/search?q=cloud%20hosting%20invoices&mode=semantic"
```

### Extracted invoice (abridged)

```json
{
  "invoice_number": "INV-20417",
  "invoice_date": "2025-03-14",
  "supplier_name": "Acme Industrial Supplies Ltd",
  "customer_name": "Riverside Home Care",
  "subtotal": 2351.0,
  "tax": 470.2,
  "total": 2821.2,
  "currency": "GBP",
  "line_items": [
    {"position": 1, "description": "Consulting services", "quantity": 10.0, "unit_price": 150.0, "amount": 1500.0},
    {"position": 2, "description": "Software license", "quantity": 2.0, "unit_price": 425.5, "amount": 851.0}
  ],
  "field_confidence": {"invoice_number": 0.95, "total": 0.85, "supplier_name": 0.72, "...": "..."},
  "raw_extraction": {"evidence": {"total": "Total (GBP) 2,821.20"}, "rejected": {}, "notes": []},
  "review_status": "ok",
  "issues": []
}
```

Fields that cannot be found are returned as `null` and never filled in by guesswork. Values an LLM proposed but that do not appear in the document are listed under `raw_extraction.rejected` and flagged with `UNGROUNDED_VALUE`.

## Validation issue codes

| Code | Severity | Meaning |
|---|---|---|
| `MISSING_FIELD` | error (number, date, supplier, total) / warning (currency) / info (customer, subtotal, tax) | Field not found |
| `TOTAL_MISMATCH` | error | subtotal + tax ≠ total (tolerance: max(0.02, 0.1%)) |
| `LINE_ITEMS_MISMATCH` | error | Σ line amounts ≠ subtotal (or total when there is no tax) |
| `LINE_ITEM_MATH` | warning | qty × unit price ≠ line amount |
| `SUBTOTAL_EXCEEDS_TOTAL`, `IMPLAUSIBLE_AMOUNT`, `INVALID_NUMBER` | error | Incorrect numeric values |
| `NEGATIVE_AMOUNT`, `ZERO_TOTAL`, `UNUSUAL_TAX_RATE` | warning | Suspicious numeric values |
| `DUPLICATE_INVOICE` | error | Same invoice number from the same supplier already exists |
| `POSSIBLE_DUPLICATE` | warning | Same supplier, date and total under a different number |
| `DUPLICATE_FILE` | warning | Byte-identical file uploaded before |
| `INVALID_DATE` / `FUTURE_DATE` / `OLD_DATE` / `AMBIGUOUS_DATE` | error / warning | Date problems |
| `UNKNOWN_CURRENCY` | warning | Not an ISO 4217 code |
| `LOW_CONFIDENCE`, `LOW_OCR_QUALITY`, `UNGROUNDED_VALUE` | warning | Extraction quality needs a human look |
| `NO_INVOICE_FOUND` | warning | Document contains no recognizable invoice |
| `NO_LINE_ITEMS` | info | No table of line items found |

An invoice with any `error` or `warning` gets `review_status = needs_review`; its document then shows `needs_review`.
