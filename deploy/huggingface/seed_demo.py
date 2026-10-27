"""Pre-load the public demo with sample documents, then reset + reseed every DEMO_RESET_HOURS.

Everything goes through the public REST API (the same path a user's upload takes), so the
seeded data is produced by the real pipeline.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import httpx

API = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
KEY = os.environ.get("API_KEYS", "").split(",")[0]
SAMPLES = Path(os.environ.get("DEMO_SAMPLES", "/opt/docintel/samples"))
RESET_HOURS = float(os.environ.get("DEMO_RESET_HOURS", "24"))

# A tour of the features: layouts, scans and photos, spreadsheets, a 20-invoice batch PDF and
# the ERP export for cross-verification, planted validation errors, a duplicate and a corrupted file.
SEED = [
    "pdf/classic_01.pdf", "pdf/modern_02.pdf", "pdf/european_01.pdf", "pdf/receipt_02.pdf",
    "pdf/statement_03.pdf", "pdf/classic_05.pdf",
    "scanned/scanned_classic_scan_01.pdf", "scanned/scanned_european_noisy_04.pdf",
    "images/modern_noisy_11.png", "images/statement_rotated90_08.png", "images/receipt_clean_01.png",
    "spreadsheets/ap_register_2025_multisheet.xlsx", "spreadsheets/eu_invoices_semicolon_latin1.csv",
    "spreadsheets/legacy_register.xls",
    "validation/total_mismatch.pdf", "validation/line_items_mismatch.pdf", "validation/duplicate_a.pdf",
    "validation/duplicate_b_rescan.png",
    "corrupted/random_bytes.pdf",
    "pdf/batch_march_20_invoices.pdf", "crossverify/erp_export_march.xlsx",
]


def log(msg: str) -> None:
    print(f"[seed] {msg}", flush=True)


def client() -> httpx.Client:
    return httpx.Client(base_url=API, headers={"X-API-Key": KEY}, timeout=120)


def wait_for_api(c: httpx.Client) -> None:
    while True:
        try:
            if c.get("/api/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)


def count_documents(c: httpx.Client) -> int:
    return c.get("/api/documents", params={"page_size": 1}).json()["meta"]["total"]


def reset(c: httpx.Client) -> None:
    while True:
        items = c.get("/api/documents", params={"page_size": 200}).json()["items"]
        if not items:
            return
        for d in items:
            c.delete(f"/api/documents/{d['id']}")


def wait_idle(c: httpx.Client, timeout_s: int = 1800) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        active = c.get("/api/documents", params={"status": "queued,processing", "page_size": 1}).json()["meta"]["total"]
        if active == 0:
            return
        time.sleep(3)


def seed(c: httpx.Client) -> None:
    ids: dict[str, str] = {}
    for rel in SEED:  # one at a time so the dashboard fills up progressively
        path = SAMPLES / rel
        if not path.exists():
            log(f"missing sample {rel}")
            continue
        r = c.post("/api/documents", files=[("files", (path.name, path.read_bytes()))])
        res = r.json()["results"][0]
        if res.get("document_id"):
            ids[path.name] = res["document_id"]
    log(f"uploaded {len(ids)} documents; waiting for processing")
    wait_idle(c)
    left, right = ids.get("batch_march_20_invoices.pdf"), ids.get("erp_export_march.xlsx")
    if left and right:
        r = c.post("/api/reconciliations", json={"left_document_id": left, "right_document_id": right})
        log(f"cross-verification: {r.json().get('summary')}")
    log("demo data ready")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true", help="keep resetting + reseeding every DEMO_RESET_HOURS")
    args = ap.parse_args()
    with client() as c:
        wait_for_api(c)
        time.sleep(3)  # let the worker connect to the broker
        if count_documents(c) == 0:
            seed(c)
        while args.loop:
            time.sleep(RESET_HOURS * 3600)
            log("scheduled reset")
            reset(c)
            seed(c)


if __name__ == "__main__":
    main()
