"""End-to-end evaluation against a running deployment.

Uploads the labeled dataset through the public API, waits for background processing,
then scores the results against ground truth:

  * extraction accuracy per field (correct / wrong / missed / hallucinated), per format
  * line-item accuracy
  * document success / failure rate, handling of corrupted files
  * validation-rule detection on planted errors, review-flag rate on clean invoices
  * processing time (per document, per page, wall clock throughput)
  * PDF-vs-Excel cross-verification against planted discrepancies
  * optional stress run (1000-page digital PDF, 100-page scanned PDF)

Usage (inside the backend container on the compose network):
    python eval/run_eval.py --api http://api:8000 --dataset eval/dataset --out eval/results --reset [--stress]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
from eval_common import FIELDS, match_invoices, same
from rapidfuzz import fuzz

from app.extraction.normalize import normalize_invoice_number

DONE = {"completed", "needs_review", "failed"}


class Api:
    def __init__(self, base: str, key: str):
        self.c = httpx.Client(base_url=base, headers={"X-API-Key": key} if key else {}, timeout=300)

    def get(self, path, **params):
        r = self.c.get(path, params=params)
        r.raise_for_status()
        return r.json()

    def post(self, path, **kw):
        r = self.c.post(path, **kw)
        r.raise_for_status()
        return r.json()

    def delete(self, path):
        self.c.delete(path)


def fmt_group(doc: dict) -> str:
    tags = doc["tags"]
    if doc["kind"] == "pdf":
        return "Scanned PDF" if "scanned" in tags else "Digital PDF"
    if doc["kind"] == "image":
        return "Image (JPG/PNG/TIFF)"
    return {"xlsx": "Excel XLSX", "xls": "Excel XLS", "csv": "CSV"}.get(doc["kind"], doc["kind"])


def reset(api: Api) -> None:
    while True:
        items = api.get("/api/documents", page_size=200)["items"]
        if not items:
            return
        for d in items:
            api.delete(f"/api/documents/{d['id']}")


def upload_all(api: Api, root: Path, docs: list[dict], batch: int = 8) -> None:
    for i in range(0, len(docs), batch):
        part = docs[i:i + batch]
        files = [("files", (Path(d["file"]).name, (root / d["file"]).read_bytes())) for d in part]
        res = api.post("/api/documents", files=files)
        for d, r in zip(part, res["results"], strict=True):
            d["_upload"] = r
            d["_id"] = r.get("document_id")


def wait_for(api: Api, ids: list[str], timeout_s: int = 3600) -> float:
    t0 = time.time()
    pending = set(ids)
    while pending and time.time() - t0 < timeout_s:
        chunk = list(pending)[:150]
        docs = api.get("/api/documents", ids=",".join(chunk), page_size=200)["items"]
        for d in docs:
            if d["status"] in DONE:
                pending.discard(d["id"])
        if pending:
            time.sleep(2)
    if pending:
        raise TimeoutError(f"{len(pending)} documents still processing")
    return time.time() - t0


def line_item_scores(pred_items: list[dict], gt_items: list[dict]) -> tuple[int, int, int, bool]:
    """(matched, predicted, expected, exact) by amount + fuzzy description."""
    remaining = list(pred_items)
    matched = 0
    for g in gt_items:
        for p in remaining:
            if same("total", p.get("amount"), g.get("amount")) and fuzz.partial_ratio(
                    (p.get("description") or "").lower(), (g.get("description") or "").lower()) >= 80:
                matched += 1
                remaining.remove(p)
                break
    exact = matched == len(gt_items) == len(pred_items)
    return matched, len(pred_items), len(gt_items), exact


def pct(n: float, d: float) -> float | None:
    return round(100.0 * n / d, 1) if d else None


def summarize_times(values: list[float]) -> dict:
    if not values:
        return {}
    s = sorted(values)
    return {
        "n": len(s), "mean_s": round(statistics.mean(s), 2), "p50_s": round(s[len(s) // 2], 2),
        "p95_s": round(s[min(len(s) - 1, int(len(s) * 0.95))], 2), "max_s": round(s[-1], 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.environ.get("EVAL_API", "http://api:8000"))
    ap.add_argument("--key", default=os.environ.get("API_KEYS", "").split(",")[0])
    ap.add_argument("--dataset", default="eval/dataset")
    ap.add_argument("--out", default="eval/results")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--stress", action="store_true")
    args = ap.parse_args()

    root, out = Path(args.dataset), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    labels = json.loads((root / "labels.json").read_text())
    api = Api(args.api, args.key)
    health = api.get("/api/health")
    if args.reset:
        reset(api)

    docs = [d for d in labels["documents"] if d["phase"] == "main"]
    t0 = time.time()
    upload_all(api, root, docs)
    ids = [d["_id"] for d in docs if d.get("_id")]
    wall = wait_for(api, ids) + 0.0
    wall_total = time.time() - t0

    # ---------------------------------------------------------------- collect results
    for d in docs:
        if not d.get("_id"):
            continue
        d["_doc"] = api.get(f"/api/documents/{d['_id']}")
        inv_list = api.get("/api/invoices", document_id=d["_id"], page_size=200)["items"]
        d["_invoices"] = [api.get(f"/api/invoices/{i['id']}") for i in inv_list]

    field_stats = {f: defaultdict(int) for f in FIELDS}
    field_by_group: dict[str, dict[str, defaultdict]] = defaultdict(lambda: {f: defaultdict(int) for f in FIELDS})
    li = {"matched": 0, "pred": 0, "gt": 0, "exact": 0, "invoices": 0}
    inv_counts = {"gt": 0, "found": 0, "spurious": 0, "all_fields_correct": 0}
    review_clean = {"clean": 0, "flagged": 0, "codes": defaultdict(int)}
    errors_detail: list[dict] = []
    doc_outcomes: list[dict] = []
    times_by_group: dict[str, list[float]] = defaultdict(list)
    pages_by_group: dict[str, int] = defaultdict(int)
    validation_checks: list[dict] = []
    dup_pair_flags: list[bool] = []

    for d in docs:
        group = fmt_group(d) if d["expect"] == "ok" else "Corrupted / unsupported"
        up = d.get("_upload", {})
        doc = d.get("_doc")
        status = doc["status"] if doc else "rejected"
        code = (doc or {}).get("error_code") or (None if up.get("accepted") else "REJECTED")
        doc_outcomes.append({"file": d["file"], "group": group, "expect": d["expect"], "status": status,
                             "error_code": code, "upload_error": up.get("error"),
                             "processing_s": round((doc or {}).get("processing_ms", 0) / 1000, 2) if doc else None,
                             "pages": (doc or {}).get("page_count"), "invoices_found": (doc or {}).get("invoice_count")})
        if doc and doc.get("processing_ms") and d["expect"] == "ok":
            times_by_group[group].append(doc["processing_ms"] / 1000)
            pages_by_group[group] += doc.get("page_count") or 0
        if d["expect"] != "ok" or not doc:
            continue

        preds = d["_invoices"]
        pairs = match_invoices(preds, d["invoices"])
        inv_counts["gt"] += len(d["invoices"])
        inv_counts["found"] += sum(1 for p, _ in pairs if p is not None)
        inv_counts["spurious"] += max(0, len(preds) - sum(1 for p, _ in pairs if p is not None))
        for pred, gt in pairs:
            all_ok = True
            for f in FIELDS:
                pv, gv = (pred or {}).get(f), gt.get(f)
                if same(f, pv, gv):
                    outcome = "correct"
                elif pv is None:
                    outcome = "missed"
                elif gv is None:
                    outcome = "hallucinated"
                else:
                    outcome = "wrong"
                field_stats[f][outcome] += 1
                field_by_group[group][f][outcome] += 1
                if gv is not None:
                    field_stats[f]["gt_present"] += 1
                if pv is not None:
                    field_stats[f]["predicted"] += 1
                if outcome != "correct":
                    all_ok = False
                    if len(errors_detail) < 400:
                        errors_detail.append({"file": d["file"], "field": f, "expected": gv, "got": pv, "outcome": outcome})
            inv_counts["all_fields_correct"] += all_ok
            if gt["line_items"]:
                m, p_n, g_n, exact = line_item_scores((pred or {}).get("line_items", []), gt["line_items"])
                li["matched"] += m
                li["pred"] += p_n
                li["gt"] += g_n
                li["exact"] += exact
                li["invoices"] += 1
            if pred is not None:
                serious = [i for i in pred["issues"] if i["severity"] in ("error", "warning")]
                if not d["expected_issues"]:
                    review_clean["clean"] += 1
                    if pred["needs_review"]:
                        review_clean["flagged"] += 1
                        for i in serious:
                            review_clean["codes"][i["code"]] += 1
                else:
                    found = {i["code"] for i in pred["issues"]}
                    for code_ in d["expected_issues"]:
                        if code_.endswith("?"):
                            dup_pair_flags.append(code_[:-1] in found)
                        else:
                            validation_checks.append({"file": d["file"], "expected": code_, "detected": code_ in found})

    def field_table(stats: dict) -> dict:
        res = {}
        for f, s in stats.items():
            n = s["correct"] + s["wrong"] + s["missed"] + s["hallucinated"]
            correct_present = s["correct"] - (n - s["gt_present"] - s["hallucinated"]) if "gt_present" in s else None
            res[f] = {
                "n": n, "accuracy_pct": pct(s["correct"], n), "correct": s["correct"], "wrong": s["wrong"],
                "missed": s["missed"], "hallucinated": s["hallucinated"],
                "precision_pct": pct(correct_present, s.get("predicted", 0)) if correct_present is not None else None,
                "recall_pct": pct(correct_present, s.get("gt_present", 0)) if correct_present is not None else None,
            }
        return res

    overall_fields = field_table(field_stats)
    total_correct = sum(v["correct"] for v in overall_fields.values())
    total_n = sum(v["n"] for v in overall_fields.values())
    by_group = {}
    for g, stats in field_by_group.items():
        n = sum(s["correct"] + s["wrong"] + s["missed"] + s["hallucinated"] for s in stats.values())
        c = sum(s["correct"] for s in stats.values())
        by_group[g] = {"field_accuracy_pct": pct(c, n), "fields_scored": n,
                       "per_field": {f: pct(s["correct"], s["correct"] + s["wrong"] + s["missed"] + s["hallucinated"])
                                     for f, s in stats.items()}}

    processable = [o for o in doc_outcomes if o["expect"] == "ok"]
    succeeded = [o for o in processable if o["status"] in ("completed", "needs_review")]
    bad_docs = [o for o in doc_outcomes if o["expect"] != "ok"]
    handled = []
    for o, d in zip(doc_outcomes, docs, strict=True):
        if d["expect"] == "ok":
            continue
        ok = (
            (d["expect"] == "reject" and o["status"] == "rejected")
            or (d["expect"] == "fail" and o["status"] == "failed" and (not d["error_code"] or o["error_code"] == d["error_code"]))
            or (d["expect"] == "fail_or_degraded" and o["status"] in ("failed", "completed", "needs_review"))
        )
        handled.append({**o, "expected_code": d["error_code"], "handled_correctly": ok})

    all_times = [t for v in times_by_group.values() for t in v]
    timing = {g: {**summarize_times(v), "pages": pages_by_group[g],
                  "sec_per_page": round(sum(v) / pages_by_group[g], 3) if pages_by_group[g] else None}
              for g, v in times_by_group.items()}

    metrics = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "environment": {"extraction_provider": health.get("extraction_provider"), "api": args.api,
                        "host_cpus": os.cpu_count(), "python": platform.python_version()},
        "dataset": {"documents": len(docs), "labeled_invoices": inv_counts["gt"],
                    "processable_documents": len(processable), "corrupted_or_unsupported": len(bad_docs)},
        "documents": {
            "success_rate_pct": pct(len(succeeded), len(processable)),
            "failure_rate_pct": pct(len(processable) - len(succeeded), len(processable)),
            "succeeded": len(succeeded), "failed": len(processable) - len(succeeded),
            "needs_review": sum(1 for o in processable if o["status"] == "needs_review"),
            "corrupted_handled_correctly": sum(h["handled_correctly"] for h in handled),
            "corrupted_total": len(handled),
        },
        "invoice_detection": {**inv_counts, "recall_pct": pct(inv_counts["found"], inv_counts["gt"]),
                              "all_fields_correct_pct": pct(inv_counts["all_fields_correct"], inv_counts["gt"])},
        "field_accuracy": {"overall_pct": pct(total_correct, total_n), "fields": overall_fields},
        "field_accuracy_by_format": by_group,
        "line_items": {"invoices_with_items": li["invoices"], "item_precision_pct": pct(li["matched"], li["pred"]),
                       "item_recall_pct": pct(li["matched"], li["gt"]),
                       "invoices_all_items_exact_pct": pct(li["exact"], li["invoices"])},
        "validation": {
            "planted_issue_checks": validation_checks,
            "planted_detected_pct": pct(sum(v["detected"] for v in validation_checks), len(validation_checks)),
            "duplicate_pair_detected": any(dup_pair_flags) if dup_pair_flags else None,
            "clean_invoices": review_clean["clean"], "clean_flagged_for_review": review_clean["flagged"],
            "clean_flagged_pct": pct(review_clean["flagged"], review_clean["clean"]),
            "clean_flag_reasons": dict(sorted(review_clean["codes"].items(), key=lambda x: -x[1])),
        },
        "timing": {"wall_clock_s": round(wall_total, 1), "processing_wait_s": round(wall, 1),
                   "throughput_docs_per_min": round(len(ids) / (wall_total / 60), 1) if wall_total else None,
                   "per_document": summarize_times(all_times), "by_format": timing},
        "corrupted_files": handled,
        "documents_detail": doc_outcomes,
        "errors_sample": errors_detail[:150],
    }

    # ---------------------------------------------------------------- cross-verification
    rec_exp = labels["reconciliation"]
    erp = next(d for d in labels["documents"] if d["phase"] == "crossverify")
    upload_all(api, root, [erp])
    wait_for(api, [erp["_id"]])
    left = next(d for d in docs if d["file"] == rec_exp["left"])
    rec = api.post("/api/reconciliations", json={"left_document_id": left["_id"], "right_document_id": erp["_id"]})
    got = {k: rec["summary"].get(k) for k in ("matched", "mismatch", "missing_in_right", "missing_in_left")}
    expected = {k: rec_exp[k] for k in got}
    planted_found = {}
    for number, fields in rec_exp["mismatched_invoices"].items():
        item = next((i for i in rec["items"] if normalize_invoice_number(i["match_key"]) == normalize_invoice_number(number)), None)
        diff_fields = {x["field"] for x in (item or {}).get("differences", [])}
        planted_found[number] = {"expected_fields": fields, "reported_fields": sorted(diff_fields),
                                 "detected": bool(item) and set(fields) <= diff_fields}
    metrics["cross_verification"] = {"expected": expected, "got": got, "planted_discrepancies": planted_found,
                                     "planted_detected": sum(v["detected"] for v in planted_found.values()),
                                     "planted_total": len(planted_found)}

    # ---------------------------------------------------------------- stress
    if args.stress and (root / "stress").exists():
        stress_res = {}
        for name in ("stress_1000_pages_digital.pdf", "stress_100_pages_scanned.pdf"):
            p = root / "stress" / name
            if not p.exists():
                continue
            t = time.time()
            r = api.post("/api/documents", files=[("files", (name, p.read_bytes()))])
            doc_id = r["results"][0]["document_id"]
            wait_for(api, [doc_id], timeout_s=7200)
            elapsed = time.time() - t
            doc = api.get(f"/api/documents/{doc_id}")
            stage_ms = {e["stage"]: e["duration_ms"] for e in doc["events"] if e["status"] == "completed" and e["duration_ms"]}
            stress_res[name] = {
                "status": doc["status"], "pages": doc["page_count"], "invoices_found": doc["invoice_count"],
                "ocr_pages": doc["meta"].get("ocr_pages"), "end_to_end_s": round(elapsed, 1),
                "processing_s": round(doc["processing_ms"] / 1000, 1),
                "pages_per_s": round(doc["page_count"] / (doc["processing_ms"] / 1000), 2),
                "stage_seconds": {k: round(v / 1000, 1) for k, v in stage_ms.items()},
            }
        meta_file = root / "stress" / "stress_meta.json"
        if meta_file.exists():
            stress_res["_meta"] = json.loads(meta_file.read_text())
        metrics["stress"] = stress_res

    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    print(json.dumps({k: metrics[k] for k in ("documents", "invoice_detection", "line_items", "timing")}, indent=2,
                     default=str)[:4000])
    print("overall field accuracy:", metrics["field_accuracy"]["overall_pct"])


if __name__ == "__main__":
    main()
