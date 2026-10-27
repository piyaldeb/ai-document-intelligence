# Evaluation report

*Generated 2026-10-27T07:36:35+00:00 by `eval/run_eval.py` + `eval/make_report.py` from a real end-to-end run against the Docker stack. Extraction provider: **rules**.*

## Method

* **Dataset:** 71 documents with 136 labeled invoices, produced by `eval/generate_dataset.py` (seeded and reproducible). It covers 5 invoice layouts, 5 currencies, US and EU number and date formats, multi-page invoices, a 20-invoice batch PDF, scanned PDFs and photos with noise, blur, skew, rotation, low resolution and low contrast, XLSX/XLS/CSV registers (multi-sheet, title rows, semicolon delimiter + decimal comma + latin-1, a malformed row), planted validation errors, and corrupted, encrypted, empty and unsupported files.
* **Procedure:** every file is uploaded through `POST /api/documents`, processed by the background worker, and read back through the public API. Predicted invoices are matched to ground truth by invoice number, falling back to total.
* **Scoring:** a field is *correct* if it matches after normalization (amounts within 0.01; names compared after case, punctuation and legal-suffix normalization with a fuzzy ratio of at least 92; dates exact). *Missed* means expected but returned null. *Hallucinated* means a value was returned where the ground truth is null. Accuracy counts a correct null as correct.
* **Caveat:** the dataset is synthetic, so the absolute numbers are optimistic compared with messy real-world scans. The harness is the reusable part: drop real labeled documents into `labels.json` to measure on production data.

## Headline results

| Metric | Result |
|---|---|
| Field-level extraction accuracy (8 fields × 136 invoices) | **99.3%** |
| Invoices with all 8 fields correct | 94.9% (129/136) |
| Invoice detection recall (incl. splitting multi-invoice PDFs) | 100.0% (136/136), spurious: 0 |
| Line items: precision / recall | 93.3% / 91.3% |
| Invoices with all line items exactly right | 87.2% of 86 |
| Document success rate (valid files) | **100.0%** (64/64) |
| Document failure rate (valid files) | 0.0% |
| Corrupted / unsupported files handled correctly | 7/7 |
| Planted validation errors detected | 100.0% |
| Duplicate invoice (PDF + rescanned PNG) detected | True |
| Clean invoices flagged for review | 14.5% (19/131) |
| Processing time per document: mean / p50 / p95 | 2.2 s / 0.67 s / 8.37 s |
| Throughput (whole batch, wall clock) | 32.0 documents/min (129.3 s total) |

## Field accuracy

| Field | Accuracy | Correct | Wrong | Missed | Hallucinated | Precision | Recall |
|---|---|---|---|---|---|---|---|
| Invoice number | 96.3% | 131 | 1 | 4 | 0 | 99.2% | 96.3% |
| Invoice date | 100.0% | 136 | 0 | 0 | 0 | 100.0% | 100.0% |
| Supplier name | 100.0% | 136 | 0 | 0 | 0 | 100.0% | 100.0% |
| Customer name | 99.3% | 135 | 0 | 1 | 0 | 100.0% | 99.2% |
| Subtotal | 100.0% | 136 | 0 | 0 | 0 | 100.0% | 100.0% |
| Tax | 100.0% | 136 | 0 | 0 | 0 | 100.0% | 100.0% |
| Total | 99.3% | 135 | 0 | 1 | 0 | 100.0% | 99.3% |
| Currency | 99.3% | 135 | 0 | 1 | 0 | 100.0% | 99.3% |

## Accuracy by input format

| Format | Fields scored | Overall | Invoice number | Invoice date | Supplier name | Customer name | Subtotal | Tax | Total | Currency |
|---|---|---|---|---|---|---|---|---|---|---|
| CSV | 144 | **100.0%** | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| Digital PDF | 432 | **100.0%** | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| Excel XLS | 80 | **100.0%** | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| Excel XLSX | 240 | **100.0%** | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| Image (JPG/PNG/TIFF) | 112 | **98.2%** | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| Scanned PDF | 80 | **92.5%** | 70.0% | 100.0% | 100.0% | 90.0% | 100.0% | 100.0% | 90.0% | 90.0% |

## Processing time

| Format | Documents | Pages | Mean (s) | p50 (s) | p95 (s) | Max (s) | Seconds per page |
|---|---|---|---|---|---|---|---|
| CSV | 2 | 2 | 1.18 | 1.65 | 1.65 | 1.65 | 1.179 |
| Digital PDF | 35 | 59 | 0.43 | 0.33 | 0.72 | 3.03 | 0.256 |
| Excel XLS | 1 | 1 | 0.79 | 0.79 | 0.79 | 0.79 | 0.792 |
| Excel XLSX | 2 | 4 | 1.65 | 2.21 | 2.21 | 2.21 | 0.823 |
| Image (JPG/PNG/TIFF) | 14 | 15 | 3.2 | 3.18 | 7.21 | 7.21 | 2.984 |
| Scanned PDF | 10 | 10 | 7.43 | 7.68 | 13.04 | 13.04 | 7.427 |

Per-document times are the worker's `processing_ms` (detect → index). Documents ran concurrently (2 worker processes, 3 OCR threads each), so the wall-clock throughput above is the more meaningful batch figure.

### Stress test: large documents

| File | Status | Pages | OCR pages | Invoices found | Results ready (s) | Pages/s | Search-indexed after (s) | Stage breakdown (s) |
|---|---|---|---|---|---|---|---|---|
| stress_1000_pages_digital.pdf | needs_review | 1000 | 0 | 1000 | 67.0 | 14.92 | 413.2 | detect 0.0, extract_text 13.9, segment 10.1, ai_extraction 27.3, validate 15.5, finalize 67.0, index 345.0 |
| stress_100_pages_scanned.pdf | needs_review | 100 | 100 | 66 | 346.3 | 0.29 | 396.3 | extract_text 337.6, segment 1.5, ai_extraction 5.7, validate 1.4, finalize 346.3, index 46.5 |

The 1000-page digital PDF contains 1000 generated invoices and the 100-page scanned PDF about 67 (the last one may be cut at the page limit). *Results ready* is when extraction and validation are finished and visible in the UI/API; the semantic search index is then built asynchronously on its own queue (*search-indexed after*, measured from upload).

## Validation

| Planted error | Expected rule | Detected |
|---|---|---|
| `validation/total_mismatch.pdf` | `TOTAL_MISMATCH` | yes |
| `validation/line_items_mismatch.pdf` | `LINE_ITEMS_MISMATCH` | yes |
| `validation/line_items_mismatch.pdf` | `LINE_ITEM_MATH` | yes |
| `validation/missing_invoice_number.pdf` | `MISSING_FIELD` | yes |
| `validation/duplicate_a.pdf` + `duplicate_b_rescan.png` | `DUPLICATE_INVOICE` | yes |

Why clean (correctly generated) invoices were still flagged for review (count of issues):

* `LINE_ITEMS_MISMATCH`: 10
* `AMBIGUOUS_DATE`: 7
* `MISSING_FIELD`: 6

## Corrupted and unsupported files

| File | Expected | Outcome | Error code | Handled correctly |
|---|---|---|---|---|
| `corrupted/truncated.pdf` | fail_or_degraded CORRUPTED_FILE | failed | CORRUPTED_FILE | yes |
| `corrupted/random_bytes.pdf` | fail CORRUPTED_FILE | failed | CORRUPTED_FILE | yes |
| `corrupted/not_a_workbook.xlsx` | fail CORRUPTED_FILE | failed | CORRUPTED_FILE | yes |
| `corrupted/empty.png` | reject EMPTY_DOCUMENT | rejected | REJECTED | yes |
| `corrupted/notes.txt` | reject UNSUPPORTED_FILE_TYPE | rejected | REJECTED | yes |
| `corrupted/truncated_photo.jpg` | fail_or_degraded  | needs_review | - | yes |
| `corrupted/password_protected.pdf` | fail ENCRYPTED_FILE | failed | ENCRYPTED_FILE | yes |

## Cross-verification (batch PDF vs. ERP Excel export)

| | Matched | Mismatch | Missing in Excel | Missing in PDF |
|---|---|---|---|---|
| Expected (planted) | 15 | 3 | 2 | 1 |
| Reported by the system | 15 | 3 | 2 | 1 |

Planted discrepancies detected with the right fields: **3/3**

* `MAR-2602`: expected ['total'], reported ['total']
* `MAR-2606`: expected ['invoice_date'], reported ['invoice_date']
* `MAR-2610`: expected ['tax', 'total'], reported ['tax', 'total']

## Error analysis (sample of incorrect fields)

| File | Field | Expected | Got | Outcome |
|---|---|---|---|---|
| `scanned/scanned_modern_scan_02.pdf` | invoice_number | SI/2025/20813 | None | missed |
| `scanned/scanned_classic_faded_06.pdf` | invoice_number | SI/2025/95393 | None | missed |
| `scanned/scanned_statement_lowres_08.pdf` | total | 8662.70 | None | missed |
| `scanned/scanned_statement_lowres_08.pdf` | currency | BDT | None | missed |
| `scanned/scanned_european_noisy_09.pdf` | customer_name | Bayview Dental Practice | None | missed |
| `scanned/scanned_classic_scan_10.pdf` | invoice_number | SI/2025/6935 | S1/2025/6935 | wrong |
| `images/modern_skewed_07.jpg` | invoice_number | SI/2025/47865 | None | missed |
| `images/classic_clean_10.jpg` | invoice_number | SI/2025/18096 | None | missed |

## Per-document outcomes

| File | Format | Status | Pages | Invoices | Time (s) |
|---|---|---|---|---|---|
| `pdf/classic_01.pdf` | Digital PDF | completed | 1 | 1 | 0.58 |
| `pdf/classic_02.pdf` | Digital PDF | completed | 1 | 1 | 0.67 |
| `pdf/classic_03.pdf` | Digital PDF | completed | 2 | 1 | 0.33 |
| `pdf/classic_04.pdf` | Digital PDF | completed | 1 | 1 | 0.35 |
| `pdf/classic_05.pdf` | Digital PDF | completed | 2 | 1 | 0.56 |
| `pdf/classic_06.pdf` | Digital PDF | completed | 1 | 1 | 0.35 |
| `pdf/modern_01.pdf` | Digital PDF | completed | 1 | 1 | 0.33 |
| `pdf/modern_02.pdf` | Digital PDF | completed | 1 | 1 | 0.27 |
| `pdf/modern_03.pdf` | Digital PDF | completed | 1 | 1 | 0.34 |
| `pdf/modern_04.pdf` | Digital PDF | completed | 1 | 1 | 0.3 |
| `pdf/modern_05.pdf` | Digital PDF | needs_review | 2 | 1 | 0.53 |
| `pdf/modern_06.pdf` | Digital PDF | completed | 1 | 1 | 0.38 |
| `pdf/european_01.pdf` | Digital PDF | completed | 1 | 1 | 0.31 |
| `pdf/european_02.pdf` | Digital PDF | completed | 1 | 1 | 0.39 |
| `pdf/european_03.pdf` | Digital PDF | needs_review | 1 | 1 | 0.39 |
| `pdf/european_04.pdf` | Digital PDF | completed | 1 | 1 | 0.29 |
| `pdf/european_05.pdf` | Digital PDF | needs_review | 2 | 1 | 0.38 |
| `pdf/european_06.pdf` | Digital PDF | completed | 1 | 1 | 0.29 |
| `pdf/receipt_01.pdf` | Digital PDF | completed | 1 | 1 | 0.38 |
| `pdf/receipt_02.pdf` | Digital PDF | completed | 1 | 1 | 0.27 |
| `pdf/receipt_03.pdf` | Digital PDF | completed | 1 | 1 | 0.19 |
| `pdf/receipt_04.pdf` | Digital PDF | completed | 1 | 1 | 0.21 |
| `pdf/receipt_05.pdf` | Digital PDF | completed | 1 | 1 | 0.32 |
| `pdf/receipt_06.pdf` | Digital PDF | completed | 1 | 1 | 0.29 |
| `pdf/statement_01.pdf` | Digital PDF | completed | 1 | 1 | 0.22 |
| `pdf/statement_02.pdf` | Digital PDF | completed | 1 | 1 | 0.2 |
| `pdf/statement_03.pdf` | Digital PDF | completed | 1 | 1 | 0.21 |
| `pdf/statement_04.pdf` | Digital PDF | completed | 1 | 1 | 0.22 |
| `pdf/statement_05.pdf` | Digital PDF | completed | 2 | 1 | 0.39 |
| `pdf/statement_06.pdf` | Digital PDF | completed | 1 | 1 | 0.21 |
| `pdf/batch_march_20_invoices.pdf` | Digital PDF | needs_review | 20 | 20 | 3.03 |
| `scanned/scanned_classic_scan_01.pdf` | Scanned PDF | completed | 1 | 1 | 13.04 |
| `scanned/scanned_modern_scan_02.pdf` | Scanned PDF | needs_review | 1 | 1 | 8.58 |
| `scanned/scanned_statement_scan_03.pdf` | Scanned PDF | completed | 1 | 1 | 7.68 |
| `scanned/scanned_european_noisy_04.pdf` | Scanned PDF | completed | 1 | 1 | 8.37 |
| `scanned/scanned_classic_skewed_05.pdf` | Scanned PDF | completed | 1 | 1 | 4.99 |
| `scanned/scanned_classic_faded_06.pdf` | Scanned PDF | needs_review | 1 | 1 | 3.81 |
| `scanned/scanned_modern_scan_07.pdf` | Scanned PDF | completed | 1 | 1 | 11.17 |
| `scanned/scanned_statement_lowres_08.pdf` | Scanned PDF | needs_review | 1 | 1 | 2.63 |
| `scanned/scanned_european_noisy_09.pdf` | Scanned PDF | completed | 1 | 1 | 7.22 |
| `scanned/scanned_classic_scan_10.pdf` | Scanned PDF | completed | 1 | 1 | 6.79 |
| `images/receipt_clean_01.png` | Image (JPG/PNG/TIFF) | completed | 1 | 1 | 1.93 |
| `images/classic_scan_02.png` | Image (JPG/PNG/TIFF) | completed | 1 | 1 | 3.18 |
| `images/modern_scan_03.jpg` | Image (JPG/PNG/TIFF) | completed | 1 | 1 | 3.46 |
| `images/statement_noisy_04.jpg` | Image (JPG/PNG/TIFF) | completed | 1 | 1 | 3.56 |
| `images/receipt_lowres_05.jpg` | Image (JPG/PNG/TIFF) | completed | 1 | 1 | 1.4 |
| `images/classic_faded_06.png` | Image (JPG/PNG/TIFF) | completed | 1 | 1 | 1.74 |
| `images/modern_skewed_07.jpg` | Image (JPG/PNG/TIFF) | needs_review | 1 | 1 | 1.59 |
| `images/statement_rotated90_08.png` | Image (JPG/PNG/TIFF) | completed | 1 | 1 | 7.21 |
| `images/receipt_scan_09.tiff` | Image (JPG/PNG/TIFF) | completed | 1 | 1 | 2.73 |
| `images/classic_clean_10.jpg` | Image (JPG/PNG/TIFF) | needs_review | 1 | 1 | 1.61 |
| `images/modern_noisy_11.png` | Image (JPG/PNG/TIFF) | needs_review | 1 | 1 | 2.62 |
| `images/statement_scan_12.jpg` | Image (JPG/PNG/TIFF) | completed | 1 | 1 | 3.46 |
| `images/classic_multipage.tiff` | Image (JPG/PNG/TIFF) | completed | 2 | 1 | 6.85 |
| `spreadsheets/ap_register_2025_multisheet.xlsx` | Excel XLSX | completed | 3 | 22 | 1.08 |
| `spreadsheets/invoice_lines_export.xlsx` | Excel XLSX | needs_review | 1 | 8 | 2.21 |
| `spreadsheets/legacy_register.xls` | Excel XLS | completed | 1 | 10 | 0.79 |
| `spreadsheets/eu_invoices_semicolon_latin1.csv` | CSV | completed | 1 | 8 | 1.65 |
| `spreadsheets/us_invoices_utf8.csv` | CSV | completed | 1 | 10 | 0.71 |
| `validation/total_mismatch.pdf` | Digital PDF | needs_review | 1 | 1 | 0.48 |
| `validation/line_items_mismatch.pdf` | Digital PDF | needs_review | 1 | 1 | 0.31 |
| `validation/missing_invoice_number.pdf` | Digital PDF | needs_review | 1 | 1 | 0.44 |
| `validation/duplicate_a.pdf` | Digital PDF | completed | 1 | 1 | 0.72 |
| `validation/duplicate_b_rescan.png` | Image (JPG/PNG/TIFF) | needs_review | 1 | 1 | 3.41 |
| `corrupted/truncated.pdf` | Corrupted / unsupported | failed (CORRUPTED_FILE) | n/a | 0 | 0.08 |
| `corrupted/random_bytes.pdf` | Corrupted / unsupported | failed (CORRUPTED_FILE) | n/a | 0 | 0.04 |
| `corrupted/not_a_workbook.xlsx` | Corrupted / unsupported | failed (CORRUPTED_FILE) | n/a | 0 | 0.03 |
| `corrupted/empty.png` | Corrupted / unsupported | rejected (REJECTED) | n/a | n/a | n/a |
| `corrupted/notes.txt` | Corrupted / unsupported | rejected (REJECTED) | n/a | n/a | n/a |
| `corrupted/truncated_photo.jpg` | Corrupted / unsupported | needs_review | 1 | 1 | 1.62 |
| `corrupted/password_protected.pdf` | Corrupted / unsupported | failed (ENCRYPTED_FILE) | n/a | 0 | 0.06 |
