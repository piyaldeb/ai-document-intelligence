# How to use DocIntel

## 1. Start it

```bash
cp .env.example .env          # set API_KEY to any random string (optional: ANTHROPIC_API_KEY)
docker compose up -d --build  # first build takes a few minutes
```

Open **http://localhost:3000**. Stop with `docker compose down` (your data is kept in Docker volumes; `docker compose down -v` wipes it).

Sample files to try are in `eval/dataset/`: `pdf/`, `scanned/`, `images/`, `spreadsheets/`, `validation/`, `crossverify/` and `corrupted/`. All of them are synthetic.

## 2. The workflow in the web app

### Step 1: Upload (Dashboard)
1. Drag files onto the upload area, or click it and choose files. You can mix PDFs, JPG/PNG/TIFF photos and XLSX/XLS/CSV files, and add many at once.
2. Click **Upload**. Each file shows *accepted* or *rejected* with a reason (e.g. unsupported type, empty file, or *duplicate of …* when the identical file was uploaded before).

### Step 2: Watch processing (Dashboard)
The documents table updates live: **queued → processing (with the current stage and a progress bar) → completed / needs review / failed**.
* *Completed*: everything was extracted and passed validation.
* *Needs review*: at least one invoice needs a human look (see Step 4).
* *Failed*: the file couldn't be processed (e.g. `CORRUPTED_FILE`, `ENCRYPTED_FILE`). Use **Reprocess** on the row, or **Retry all failed**.

### Step 3: Inspect a document (click its name)
* **Invoices:** every invoice found in the file. A 1000-page batch PDF is split into its individual invoices.
* **Extracted text:** the text of each page or sheet. Each page says whether its text came from the PDF's text layer or from OCR, and shows the OCR confidence.
* **Processing history:** each pipeline stage with its duration, for every attempt.
* **Original file:** the PDF or image itself, for comparison.

### Step 4: Review and correct (Review queue → invoice)
1. **Review queue** lists the invoices that need attention, worst first.
2. On an invoice, each field (number, date, supplier, customer, subtotal, tax, total, currency) shows:
   * a **confidence badge** (green: high, amber: medium, red: low, grey: not found),
   * the **evidence**: the exact text in the document the value came from,
   * any value the AI proposed but that is **not in the document**, which is discarded and shown so you can decide.
3. The **issues panel** explains what is wrong, e.g. *"Subtotal + tax = 2,821.20 but total is 2,921.20"* or *"Invoice INV-1 from this supplier already exists"*.
4. Fix values (and line items) as needed, optionally add a reason, and **Save**. The invoice is re-validated immediately and the change goes into the **correction history** (old → new, who, why).
5. Click **Approve invoice**. While errors remain you'll be asked to correct them or choose **Approve anyway**.

### Step 5: Find things (Invoices / Search)
* **Invoices** page: filter by keyword, supplier, currency, date range, amount range, review status or issue type, and sort by date, total or number of issues.
* **Search** page: type what you're looking for in plain words, e.g. *"cloud hosting invoices from Kestrel"*.
  * *Hybrid* (default) combines both approaches below.
  * *Keyword* matches exact words and numbers, such as an invoice number.
  * *Semantic* matches by meaning, e.g. "licence renewal" finds "Software license (annual)".

### Step 6: Cross-verify two documents (Cross-verify)
1. Pick the **left** document (e.g. the supplier's PDF batch) and the **right** one (e.g. your ERP's Excel export). Both must be processed.
2. Optionally set the amount tolerance, then click **Run**.
3. You get **matched**, **mismatched** (each differing field shown left vs right), **missing in left** and **missing in right**.

Try it with `pdf/batch_march_20_invoices.pdf` vs `crossverify/erp_export_march.xlsx`. The Excel file has 3 deliberately altered invoices, 2 missing ones and 1 extra.

## 3. Using the API instead of the UI

Everything in the UI is also a REST call (see [api.md](api.md); interactive docs at http://localhost:3000/api/docs (via the web app, no key needed) or http://localhost:8000/api/docs (click *Authorize* and paste your `API_KEY`)).

```bash
KEY=<your API_KEY>
# upload
curl -H "X-API-Key: $KEY" -F files=@invoice.pdf -F files=@register.xlsx http://localhost:8000/api/documents
# status
curl -H "X-API-Key: $KEY" http://localhost:8000/api/documents/<document_id>/status
# extracted invoices of a document (JSON)
curl -H "X-API-Key: $KEY" "http://localhost:8000/api/invoices?document_id=<document_id>"
# correct a field
curl -X PATCH -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"total":"2821.20","reason":"typo on scan"}' http://localhost:8000/api/invoices/<invoice_id>
```

## 4. Turning on Claude extraction

Put your key in `.env` (`ANTHROPIC_API_KEY=sk-ant-...`) and run `docker compose up -d`. New documents are then extracted by Claude, with the grounding check and rules cross-check as safety nets; the dashboard shows the active provider. Without a key, the built-in rules extractor is used.

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| UI shows "backend unreachable" | `docker compose ps`; the API needs Postgres and Redis healthy. Check `docker compose logs api`. |
| Documents stay *queued* | The worker isn't running: `docker compose logs worker`, then `docker compose up -d worker`. |
| 401 from the API | The `X-API-Key` header must equal `API_KEY` in `.env`. |
| Slow OCR on big scans | Raise `OCR_WORKERS` / `WORKER_CONCURRENCY` in `.env`, or `docker compose up -d --scale worker=3`. |
| Start fresh | `docker compose down -v && docker compose up -d` |
