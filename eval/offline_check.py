"""Fast offline extraction check (no API/queue/DB): run text extraction + segmentation +
extraction directly on dataset files and print every field that differs from the labels.

Developer tool for iterating on extractors; the official numbers come from run_eval.py.
    python eval/offline_check.py --dataset eval/dataset [--only pdf/ scanned/ ...] [--provider rules]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval_common import FIELDS, match_invoices, same

from app.extraction import service
from app.pipeline.detect import detect_file
from app.pipeline.images import extract_image
from app.pipeline.pdf import extract_pdf
from app.pipeline.processor import build_units
from app.pipeline.spreadsheet import extract_spreadsheet


def extract(path: Path, provider: str):
    kind = detect_file(path, path.name).kind
    if kind == "pdf":
        res = extract_pdf(path)
    elif kind == "image":
        res = extract_image(path)
    else:
        res = extract_spreadsheet(path, kind)
    # Same candidate building as the worker; extraction without the DB/queue.
    return [u.data or service.extract_text(u.text, provider=provider) for u in build_units(res)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="eval/dataset")
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--provider", default="rules")
    args = ap.parse_args()
    root = Path(args.dataset)
    labels = json.loads((root / "labels.json").read_text())["documents"]
    total = correct = 0
    for doc in labels:
        if doc["expect"] != "ok" or (args.only and not any(doc["file"].startswith(o) for o in args.only)):
            continue
        preds = [p.model_dump(mode="json") for p in extract(root / doc["file"], args.provider)]
        pairs = match_invoices(preds, doc["invoices"])
        if len(preds) != len(doc["invoices"]):
            print(f"{doc['file']}: {len(preds)} invoices found, {len(doc['invoices'])} expected")
        for pred, gt in pairs:
            for f in FIELDS:
                total += 1
                if same(f, (pred or {}).get(f), gt.get(f)):
                    correct += 1
                else:
                    print(f"{doc['file']} [{gt['invoice_number']}] {f}: got {(pred or {}).get(f)!r} expected {gt.get(f)!r}")
    print(f"\nfield accuracy {correct}/{total} = {100 * correct / max(1, total):.1f}%")


if __name__ == "__main__":
    main()
