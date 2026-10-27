# Test results

The backend test-suite runs with pytest inside the backend Docker image (Python 3.12, Tesseract 5.3) against a dedicated `docintel_test` PostgreSQL + pgvector database. Reproduce with:

```bash
./scripts/run-tests.sh
```

**Result: 98 passed in 123.08s (0:02:03) · line coverage 91%**

The API tests run the background job synchronously: the queue's `enqueue` is patched to call the pipeline directly. So each API test exercises upload → detection → text extraction/OCR → segmentation → extraction → validation → embedding/indexing → database → API response, with no mocks in between. Only the Anthropic API is mocked, in the extraction tests, because no API key is available in CI.

## Suites

| File | Tests | Covers |
|---|---|---|
| `tests/test_api.py` | 16 (16 passed) | REST API end-to-end through the real pipeline: auth, multi-upload + rejection, status/history/pages/file, extracted JSON, corrections + audit + re-validation, approval rules, duplicate invoices & files, filters, keyword/semantic/hybrid search, PDF↔Excel cross-verification, failed-job reprocessing, retry-all, contained internal errors, stats |
| `tests/test_extraction.py` | 11 (11 passed) | AI extraction: rules extractor on 4 layouts, Claude extractor with mocked API (schema mapping, grounding/hallucination rejection, rules cross-check, fallback on API failure, prompt-injection fencing, refusal/truncation handling) |
| `tests/test_normalize_detect_layout.py` | 42 (42 passed) | Amount/date/currency parsing, identifier normalisation, content-based file-type detection, layout reconstruction |
| `tests/test_processing.py` | 19 (19 passed) | Document processing: PDF text layer, OCR on scans and poor-quality images (noise, low-res, 90° rotation, multi-page TIFF, truncated JPEG), spreadsheet parsing (multi-sheet XLSX, XLS, CSV encodings/delimiters/malformed rows), corrupted & encrypted files, multi-invoice segmentation |
| `tests/test_validation.py` | 10 (10 passed) | Validation rules: missing fields, arithmetic consistency, line items, numeric sanity, dates, duplicates, confidence and OCR-quality flags |

## Test cases

### `tests/test_api.py`

- ✅ `test_auth_required`
- ✅ `test_upload_multiple_and_reject_unsupported`
- ✅ `test_document_detail_status_pages_history_and_file`
- ✅ `test_extracted_invoice_json`
- ✅ `test_validation_errors_correction_audit_and_approval`
- ✅ `test_correction_rejects_unknown_fields_and_bad_values`
- ✅ `test_line_item_correction_revalidates`
- ✅ `test_duplicate_invoice_across_documents`
- ✅ `test_duplicate_file_upload_is_flagged`
- ✅ `test_invoice_filters`
- ✅ `test_keyword_semantic_and_hybrid_search`
- ✅ `test_pdf_vs_excel_cross_verification`
- ✅ `test_failed_job_and_reprocessing`
- ✅ `test_retry_all_failed_and_delete`
- ✅ `test_unexpected_errors_are_contained`
- ✅ `test_stats`

### `tests/test_extraction.py`

- ✅ `test_rules_classic_layout`
- ✅ `test_rules_side_by_side_parties_and_indexed_table`
- ✅ `test_rules_european_number_format`
- ✅ `test_rules_missing_values_stay_null`
- ✅ `test_llm_result_mapping_and_grounding_rejects_hallucinations`
- ✅ `test_service_merges_llm_with_rules_cross_check`
- ✅ `test_service_lowers_confidence_on_disagreement`
- ✅ `test_service_falls_back_to_rules_when_llm_fails`
- ✅ `test_llm_prompt_wraps_document_as_data`
- ✅ `test_llm_unusable_responses_raise[refusal]`
- ✅ `test_llm_unusable_responses_raise[max_tokens]`

### `tests/test_normalize_detect_layout.py`

- ✅ `test_parse_amount[1,234.56-1234.56]`
- ✅ `test_parse_amount[1.234,56-1234.56]`
- ✅ `test_parse_amount[$1,234.56-1234.56]`
- ✅ `test_parse_amount[\u20ac 99,90-99.90]`
- ✅ `test_parse_amount[USD 2,500-2500]`
- ✅ `test_parse_amount[(120.00)--120.00]`
- ✅ `test_parse_amount[1'234.50-1234.50]`
- ✅ `test_parse_amount[12-12]`
- ✅ `test_parse_amount[0.5-0.5]`
- ✅ `test_parse_amount[Rs. 4,500.00-4500.00]`
- ✅ `test_parse_amount[1,234,567.89-1234567.89]`
- ✅ `test_parse_amount[-45.10--45.10]`
- ✅ `test_parse_amount_rejects_non_numbers[abc]`
- ✅ `test_parse_amount_rejects_non_numbers[]`
- ✅ `test_parse_amount_rejects_non_numbers[None]`
- ✅ `test_parse_amount_rejects_non_numbers[12/03/2025]`
- ✅ `test_parse_amount_rejects_non_numbers[1,23,4]`
- ✅ `test_parse_amount_rejects_non_numbers[N/A]`
- ✅ `test_parse_amount_three_decimals_uses_document_convention`
- ✅ `test_find_amounts_skips_percentages_dates_and_ids`
- ✅ `test_find_dates[2025-03-14-True-expected0-False]`
- ✅ `test_find_dates[14/03/2025-True-expected1-False]`
- ✅ `test_find_dates[03/14/2025-True-expected2-False]`
- ✅ `test_find_dates[03/04/2025-True-expected3-True]`
- ✅ `test_find_dates[03/04/2025-False-expected4-True]`
- ✅ `test_find_dates[14.03.2025-True-expected5-False]`
- ✅ `test_find_dates[March 14, 2025-True-expected6-False]`
- ✅ `test_find_dates[14 Mar 2025-True-expected7-False]`
- ✅ `test_find_dates[1st February 2025-True-expected8-False]`
- ✅ `test_parse_date_excel_serial_and_invalid`
- ✅ `test_currency_detection`
- ✅ `test_identifier_normalisation`
- ✅ `test_detect_by_content[%PDF-1.7\n...-a.pdf-pdf]`
- ✅ `test_detect_by_content[\x89PNG\r\n\x1a\n....-a.png-image]`
- ✅ `test_detect_by_content[\xff\xd8\xff\xe0....-photo.jpeg-image]`
- ✅ `test_detect_by_content[II*\x00....-scan.tif-image]`
- ✅ `test_detect_by_content[\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1....-old.xls-xls]`
- ✅ `test_detect_by_content[PK\x03\x04....-book.xlsx-xlsx]`
- ✅ `test_detect_by_content[a,b,c\n1,2,3\n-data.csv-csv]`
- ✅ `test_detect_by_content[%PDF-1.4-renamed.png-pdf]`
- ✅ `test_detect_errors`
- ✅ `test_words_to_text_preserves_columns`

### `tests/test_processing.py`

- ✅ `test_digital_pdf_uses_text_layer`
- ✅ `test_scanned_pdf_falls_back_to_ocr`
- ✅ `test_ocr_images_including_poor_quality[clean.png-None]`
- ✅ `test_ocr_images_including_poor_quality[noisy.jpg-noisy]`
- ✅ `test_ocr_images_including_poor_quality[small.png-lowres]`
- ✅ `test_ocr_images_including_poor_quality[rot.tiff-rotated90]`
- ✅ `test_multipage_tiff`
- ✅ `test_truncated_jpeg_is_recovered_with_warning`
- ✅ `test_corrupted_files_raise_typed_errors[pdf_truncated-exc0]`
- ✅ `test_corrupted_files_raise_typed_errors[pdf_garbage-exc1]`
- ✅ `test_corrupted_files_raise_typed_errors[pdf_encrypted-exc2]`
- ✅ `test_corrupted_files_raise_typed_errors[xlsx_garbage-exc3]`
- ✅ `test_corrupted_files_raise_typed_errors[png_garbage-exc4]`
- ✅ `test_xlsx_multisheet_register_with_title_rows`
- ✅ `test_xlsx_line_level_export_groups_rows`
- ✅ `test_legacy_xls`
- ✅ `test_csv_semicolon_latin1_decimal_comma_and_bad_rows`
- ✅ `test_form_style_sheet_is_left_to_text_extraction`
- ✅ `test_segmentation_of_multi_invoice_pdf`

### `tests/test_validation.py`

- ✅ `test_clean_invoice_passes`
- ✅ `test_missing_required_fields_are_errors`
- ✅ `test_missing_optional_fields_are_informational_except_currency`
- ✅ `test_total_mismatch`
- ✅ `test_rounding_within_tolerance_is_accepted`
- ✅ `test_line_items_sum_and_line_math`
- ✅ `test_numeric_sanity_rules`
- ✅ `test_date_rules`
- ✅ `test_duplicates_and_quality_flags`
- ✅ `test_unknown_currency`

## Coverage (statements; files at 100% omitted)

```
Name                                   Stmts   Miss  Cover   Missing
app/api/documents.py                     138     14    90%   46, 60-62, 107, 109, 111-114, 124, 169, 182, 194
app/api/invoices.py                      103      9    91%   80, 98-100, 118, 120, 123, 130, 149
app/api/reconciliation.py                 47      5    89%   46, 48, 56-57, 65
app/api/search.py                         22      1    95%   39
app/config.py                             55      1    98%   75
app/db.py                                 26      8    69%   38-46
app/extraction/columns.py                 19      1    95%   59
app/extraction/grounding.py               56     13    77%   46, 49, 61-68, 90-91, 93
app/extraction/llm.py                    122     28    77%   61-67, 88-93, 101, 109-113, 117, 119, 121, 123, 125, 132, 145-147, 153-154, 162, 175
app/extraction/normalize.py              210     25    88%   40, 43-44, 59, 63-64, 80, 95, 103-106, 111-112, 171, 190-191, 201, 205, 213, 236, 255, 259-260, 274, 281
app/extraction/rules.py                  346     34    90%   131, 161, 176, 179, 181, 199-201, 204, 212-219, 226, 228, 230, 285, 291, 310, 314, 341, 343-344, 368, 395, 412, 438, 467-470
app/extraction/service.py                 46      2    96%   18, 32
app/extraction/spreadsheet_mapper.py     127     14    89%   37, 47, 49, 54, 59, 81, 101-104, 126-127, 137-138
app/pipeline/detect.py                    66      4    94%   52, 55, 76, 96
app/pipeline/errors.py                    23      2    91%   14, 16
app/pipeline/images.py                    43      3    93%   27, 40-41
app/pipeline/ocr.py                      122      9    93%   44, 57-58, 91, 100, 114-115, 149, 172
app/pipeline/pdf.py                       92     17    82%   52, 61, 76-78, 81, 89-92, 101-104, 108-109, 118
app/pipeline/processor.py                216     12    94%   142, 156-157, 176, 213, 225-226, 228, 257, 300, 302-303
app/pipeline/segment.py                   44      3    93%   47, 49, 51
app/pipeline/spreadsheet.py              157     25    84%   31, 35, 48, 50, 64, 77, 83-85, 104-107, 117-123, 149-150, 180, 192, 205
app/search/embeddings.py                  40      1    98%   33
app/search/service.py                    139      7    95%   50, 58, 66, 82, 101, 197, 215
app/security.py                           44     15    66%   21-23, 29, 41-51
app/services/reconcile.py                 93     19    80%   25, 28-30, 35, 37, 53, 60, 83-84, 98-108
app/storage.py                            42      6    86%   42, 47-49, 57-58
app/validation/rules.py                  123      5    96%   101, 103, 137-138, 187
TOTAL                                   3175    283    91%
```

## Slowest tests

```
9.77s call     tests/test_api.py::test_upload_multiple_and_reject_unsupported
8.68s call     tests/test_api.py::test_duplicate_invoice_across_documents
8.27s setup    tests/test_api.py::test_auth_required
6.73s call     tests/test_processing.py::test_ocr_images_including_poor_quality[rot.tiff-rotated90]
4.49s call     tests/test_processing.py::test_scanned_pdf_falls_back_to_ocr
3.48s call     tests/test_api.py::test_validation_errors_correction_audit_and_approval
3.34s call     tests/test_api.py::test_retry_all_failed_and_delete
2.76s call     tests/test_processing.py::test_ocr_images_including_poor_quality[noisy.jpg-noisy]
```

The frontend is verified with `npm run build` (TypeScript strict type-check plus ESLint) and the end-to-end walkthrough in [walkthrough/](walkthrough/).
