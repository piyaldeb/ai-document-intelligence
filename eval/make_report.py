"""Render eval/results/metrics.json as a Markdown evaluation report (no hand-typed numbers)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

LABELS = {
    "invoice_number": "Invoice number", "invoice_date": "Invoice date", "supplier_name": "Supplier name",
    "customer_name": "Customer name", "subtotal": "Subtotal", "tax": "Tax", "total": "Total", "currency": "Currency",
}


def v(x, suffix=""):
    return "n/a" if x is None else f"{x}{suffix}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", default="eval/results/metrics.json")
    ap.add_argument("--out", default="eval/results/evaluation-report.md")
    args = ap.parse_args()
    m = json.loads(Path(args.metrics).read_text())
    d, inv, fa, li, val, t = (m["documents"], m["invoice_detection"], m["field_accuracy"], m["line_items"],
                              m["validation"], m["timing"])
    L: list[str] = []
    w = L.append
    w("# Evaluation report")
    w("")
    w(f"*Generated {m['generated_at']} by `eval/run_eval.py` + `eval/make_report.py` from a real end-to-end run "
      f"against the Docker stack. Extraction provider: **{m['environment']['extraction_provider']}**.*")
    w("")
    w("## Method")
    w("")
    w(f"* **Dataset:** {m['dataset']['documents']} documents with {m['dataset']['labeled_invoices']} labeled invoices, produced by "
      "`eval/generate_dataset.py` (seeded and reproducible). It covers 5 invoice layouts, 5 currencies, US and EU number and "
      "date formats, multi-page invoices, a 20-invoice batch PDF, scanned PDFs and photos with noise, blur, skew, rotation, "
      "low resolution and low contrast, XLSX/XLS/CSV registers (multi-sheet, title rows, semicolon delimiter + decimal comma + "
      "latin-1, a malformed row), planted validation errors, and corrupted, encrypted, empty and unsupported files.")
    w("* **Procedure:** every file is uploaded through `POST /api/documents`, processed by the background worker, and read "
      "back through the public API. Predicted invoices are matched to ground truth by invoice number, falling back to total.")
    w("* **Scoring:** a field is *correct* if it matches after normalization (amounts within 0.01; names compared after "
      "case, punctuation and legal-suffix normalization with a fuzzy ratio of at least 92; dates exact). "
      "*Missed* means expected but returned null. *Hallucinated* means a value was returned where the ground truth is null. "
      "Accuracy counts a correct null as correct.")
    w("* **Caveat:** the dataset is synthetic, so the absolute numbers are optimistic compared with messy real-world scans. "
      "The harness is the reusable part: drop real labeled documents into `labels.json` to measure on production data.")
    w("")
    w("## Headline results")
    w("")
    w("| Metric | Result |")
    w("|---|---|")
    w(f"| Field-level extraction accuracy (8 fields × {inv['gt']} invoices) | **{v(fa['overall_pct'], '%')}** |")
    w(f"| Invoices with all 8 fields correct | {v(inv['all_fields_correct_pct'], '%')} ({inv['all_fields_correct']}/{inv['gt']}) |")
    w(f"| Invoice detection recall (incl. splitting multi-invoice PDFs) | {v(inv['recall_pct'], '%')} ({inv['found']}/{inv['gt']}), spurious: {inv['spurious']} |")
    w(f"| Line items: precision / recall | {v(li['item_precision_pct'], '%')} / {v(li['item_recall_pct'], '%')} |")
    w(f"| Invoices with all line items exactly right | {v(li['invoices_all_items_exact_pct'], '%')} of {li['invoices_with_items']} |")
    w(f"| Document success rate (valid files) | **{v(d['success_rate_pct'], '%')}** ({d['succeeded']}/{d['succeeded'] + d['failed']}) |")
    w(f"| Document failure rate (valid files) | {v(d['failure_rate_pct'], '%')} |")
    w(f"| Corrupted / unsupported files handled correctly | {d['corrupted_handled_correctly']}/{d['corrupted_total']} |")
    w(f"| Planted validation errors detected | {v(val['planted_detected_pct'], '%')} |")
    w(f"| Duplicate invoice (PDF + rescanned PNG) detected | {v(val['duplicate_pair_detected'])} |")
    w(f"| Clean invoices flagged for review | {v(val['clean_flagged_pct'], '%')} ({val['clean_flagged_for_review']}/{val['clean_invoices']}) |")
    pd_ = t["per_document"]
    w(f"| Processing time per document: mean / p50 / p95 | {v(pd_.get('mean_s'))} s / {v(pd_.get('p50_s'))} s / {v(pd_.get('p95_s'))} s |")
    w(f"| Throughput (whole batch, wall clock) | {v(t['throughput_docs_per_min'])} documents/min ({t['wall_clock_s']} s total) |")
    w("")
    w("## Field accuracy")
    w("")
    w("| Field | Accuracy | Correct | Wrong | Missed | Hallucinated | Precision | Recall |")
    w("|---|---|---|---|---|---|---|---|")
    for f, s in fa["fields"].items():
        w(f"| {LABELS[f]} | {v(s['accuracy_pct'], '%')} | {s['correct']} | {s['wrong']} | {s['missed']} | {s['hallucinated']} | "
          f"{v(s['precision_pct'], '%')} | {v(s['recall_pct'], '%')} |")
    w("")
    w("## Accuracy by input format")
    w("")
    fields = list(LABELS)
    w("| Format | Fields scored | Overall | " + " | ".join(LABELS[f] for f in fields) + " |")
    w("|---|---|---|" + "---|" * len(fields))
    for g, s in sorted(m["field_accuracy_by_format"].items()):
        w(f"| {g} | {s['fields_scored']} | **{v(s['field_accuracy_pct'], '%')}** | " +
          " | ".join(v(s["per_field"].get(f), "%") for f in fields) + " |")
    w("")
    w("## Processing time")
    w("")
    w("| Format | Documents | Pages | Mean (s) | p50 (s) | p95 (s) | Max (s) | Seconds per page |")
    w("|---|---|---|---|---|---|---|---|")
    for g, s in sorted(t["by_format"].items()):
        w(f"| {g} | {s.get('n')} | {s.get('pages')} | {s.get('mean_s')} | {s.get('p50_s')} | {s.get('p95_s')} | {s.get('max_s')} | {v(s.get('sec_per_page'))} |")
    w("")
    w("Per-document times are the worker's `processing_ms` (detect → index). Documents ran concurrently "
      "(2 worker processes, 3 OCR threads each), so the wall-clock throughput above is the more meaningful batch figure.")
    if m.get("stress"):
        w("")
        w("### Stress test: large documents")
        w("")
        w("| File | Status | Pages | OCR pages | Invoices found | Results ready (s) | Pages/s | Search-indexed after (s) | Stage breakdown (s) |")
        w("|---|---|---|---|---|---|---|---|---|")
        for name, s in m["stress"].items():
            if name.startswith("_"):
                continue
            stages = ", ".join(f"{k} {x}" for k, x in s["stage_seconds"].items())
            w(f"| {name} | {s['status']} | {s['pages']} | {s['ocr_pages']} | {s['invoices_found']} | {s['processing_s']} | {s['pages_per_s']} | {s.get('search_indexed_after_s', 'n/a')} | {stages} |")
        meta = m["stress"].get("_meta")
        if meta:
            w("")
            w(f"The 1000-page digital PDF contains {meta.get('digital_invoices_approx')} generated invoices and the 100-page scanned PDF "
              f"about {meta.get('scanned_invoices_approx', 'n/a')} (the last one may be cut at the page limit). *Results ready* is when "
              "extraction and validation are finished and visible in the UI/API; the semantic search index is then built "
              "asynchronously on its own queue (*search-indexed after*, measured from upload).")
    w("")
    w("## Validation")
    w("")
    w("| Planted error | Expected rule | Detected |")
    w("|---|---|---|")
    for c in val["planted_issue_checks"]:
        w(f"| `{c['file']}` | `{c['expected']}` | {'yes' if c['detected'] else '**no**'} |")
    w(f"| `validation/duplicate_a.pdf` + `duplicate_b_rescan.png` | `DUPLICATE_INVOICE` | {'yes' if val['duplicate_pair_detected'] else '**no**'} |")
    w("")
    if val["clean_flag_reasons"]:
        w("Why clean (correctly generated) invoices were still flagged for review (count of issues):")
        w("")
        for code, n in val["clean_flag_reasons"].items():
            w(f"* `{code}`: {n}")
        w("")
    w("## Corrupted and unsupported files")
    w("")
    w("| File | Expected | Outcome | Error code | Handled correctly |")
    w("|---|---|---|---|---|")
    for h in m["corrupted_files"]:
        w(f"| `{h['file']}` | {h['expect']} {h['expected_code'] or ''} | {h['status']} | {h['error_code'] or h.get('upload_error') or '-'} | {'yes' if h['handled_correctly'] else '**no**'} |")
    w("")
    cv = m.get("cross_verification")
    if cv:
        w("## Cross-verification (batch PDF vs. ERP Excel export)")
        w("")
        w("| | Matched | Mismatch | Missing in Excel | Missing in PDF |")
        w("|---|---|---|---|---|")
        e, g = cv["expected"], cv["got"]
        w(f"| Expected (planted) | {e['matched']} | {e['mismatch']} | {e['missing_in_right']} | {e['missing_in_left']} |")
        w(f"| Reported by the system | {g['matched']} | {g['mismatch']} | {g['missing_in_right']} | {g['missing_in_left']} |")
        w("")
        w(f"Planted discrepancies detected with the right fields: **{cv['planted_detected']}/{cv['planted_total']}**")
        w("")
        for num, p in cv["planted_discrepancies"].items():
            w(f"* `{num}`: expected {p['expected_fields']}, reported {p['reported_fields']}")
        w("")
    w("## Error analysis (sample of incorrect fields)")
    w("")
    w("| File | Field | Expected | Got | Outcome |")
    w("|---|---|---|---|---|")
    for e in m["errors_sample"][:60]:
        w(f"| `{e['file']}` | {e['field']} | {e['expected']} | {e['got']} | {e['outcome']} |")
    w("")
    w("## Per-document outcomes")
    w("")
    w("| File | Format | Status | Pages | Invoices | Time (s) |")
    w("|---|---|---|---|---|---|")
    for o in m["documents_detail"]:
        w(f"| `{o['file']}` | {o['group']} | {o['status']}{' (' + o['error_code'] + ')' if o['error_code'] else ''} | {v(o['pages'])} | {v(o['invoices_found'])} | {v(o['processing_s'])} |")
    Path(args.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
