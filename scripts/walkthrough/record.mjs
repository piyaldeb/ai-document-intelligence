// Records a captioned walkthrough of the running app as a video (docs/walkthrough/walkthrough.webm).
// Prerequisites: `docker compose up -d` (web on http://localhost:3000), then:
//   cd scripts/walkthrough && npm install && npx playwright install chromium && npm run record
import { chromium } from "playwright";
import { mkdirSync, readdirSync, renameSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const dataset = path.join(root, "eval/dataset");
const outDir = path.join(root, "docs/walkthrough");
const BASE = process.env.WEB_URL ?? "http://localhost:3000";
// Read-only helper calls go through the web app's proxy (it adds the API key server-side).
const API = process.env.API_URL ?? BASE;
const KEY = process.env.API_KEY ?? "";

// The demo is pre-seeded (see deploy/huggingface/seed_demo.py); upload a few new files on top.
const UPLOADS = [
  "pdf/modern_04.pdf",
  "images/classic_scan_02.png",
  "scanned/scanned_modern_scan_07.pdf",
  "spreadsheets/us_invoices_utf8.csv",
  "pdf/classic_01.pdf",
].map((f) => path.join(dataset, f));

const pause = (ms) => new Promise((r) => setTimeout(r, ms));

async function caption(page, text) {
  await page.evaluate((t) => {
    let el = document.getElementById("__walkthrough_caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "__walkthrough_caption";
      Object.assign(el.style, {
        position: "fixed", left: "50%", bottom: "18px", transform: "translateX(-50%)", zIndex: "2147483647",
        background: "rgba(26,54,93,0.94)", color: "#fff", padding: "10px 18px", borderRadius: "10px",
        font: "600 15px/1.35 system-ui, sans-serif", maxWidth: "90vw", textAlign: "center",
        boxShadow: "0 6px 24px rgba(0,0,0,.25)", borderLeft: "5px solid #d97706", pointerEvents: "none",
      });
      document.body.appendChild(el);
    }
    el.textContent = t;
  }, text);
}

async function step(page, text, ms = 2600) {
  await caption(page, text);
  await pause(ms);
}

async function goto(page, url) {
  await page.goto(BASE + url, { waitUntil: "networkidle" });
}

async function apiJson(pathname) {
  const r = await fetch(API + pathname, { headers: KEY ? { "X-API-Key": KEY } : {} });
  return r.json();
}

async function waitForProcessing(timeoutMs = 240_000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const d = await apiJson("/api/documents?status=queued,processing&page_size=1");
    if (d.meta.total === 0) return;
    await pause(1500);
  }
}

async function main() {
  mkdirSync(outDir, { recursive: true });
  const tmpVideo = path.join(outDir, "_raw");
  rmSync(tmpVideo, { recursive: true, force: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: tmpVideo, size: { width: 1440, height: 900 } },
  });
  const page = await context.newPage();

  await goto(page, "/");
  await step(page, "DocIntel: AI document intelligence. Dashboard with live processing statistics", 3500);

  await page.locator('input[type="file"]').setInputFiles(UPLOADS);
  await step(page, "1 · Upload several files at once: digital PDF, scanned PDF, photo, CSV, and one we already have (duplicate)", 3500);
  await page.getByRole("button", { name: /^upload/i }).first().click();
  await step(page, "Files stream to the API; each one is queued for background processing (Celery + Redis)", 4000);
  await step(page, "2 · Live progress: detect → text/OCR → split invoices → AI extraction → validation → indexing", 6000);
  await waitForProcessing();
  await page.reload({ waitUntil: "networkidle" });
  await step(page, "Done: completed or flagged for review. Earlier, a corrupted PDF failed safely with CORRUPTED_FILE (see Failed)", 5000);

  // Document detail: batch PDF
  const batchDoc = (await apiJson("/api/documents?q=batch_march&page_size=1")).items[0];
  await goto(page, `/documents/${batchDoc.id}`);
  await step(page, "3 · A 20-invoice batch PDF was split into separate invoices automatically", 4000);
  for (const tab of [/extracted text/i, /history/i, /original/i]) {
    const t = page.getByRole("tab", { name: tab }).first();
    if (await t.count()) {
      await t.click();
      await step(page, tab.source.includes("text") ? "Layout-preserving extracted text per page (text layer or OCR)"
        : tab.source.includes("history") ? "Processing history: every stage with its duration, for every attempt"
        : "The original document, side by side", 3500);
    }
  }

  // Review queue → invoice with total mismatch
  await goto(page, "/review");
  await step(page, "4 · Review queue: records that need a human, sorted by severity", 4000);
  await goto(page, "/invoices?q=" + encodeURIComponent(""));
  const mismatch = await apiJson("/api/invoices?issue_code=TOTAL_MISMATCH&page_size=1");
  if (mismatch.items?.length) {
    const inv = mismatch.items[0];
    await goto(page, `/invoices/${inv.id}`);
    await step(page, "Extracted JSON fields with confidence + evidence; validation found subtotal + tax ≠ total", 5000);
    await page.mouse.wheel(0, 500);
    await step(page, "Line items and validation issues (errors, warnings) are shown next to the fields they affect", 4000);
    await page.mouse.wheel(0, -500);
    const total = page.getByLabel(/^total/i).first();
    if (await total.count()) {
      const expected = (Number(inv.subtotal) + Number(inv.tax)).toFixed(2);
      await total.fill(expected);
      await step(page, `5 · Correct a value (total → ${expected})…`, 2500);
      const save = page.getByRole("button", { name: /save/i }).first();
      await save.click();
      await page.waitForLoadState("networkidle");
      await pause(1500);
      await step(page, "…the change is audited (old → new, who, why) and the invoice is re-validated instantly", 4500);
      const approve = page.getByRole("button", { name: /approve invoice/i }).first();
      if (await approve.isEnabled().catch(() => false)) {
        await approve.click();
        await step(page, "Approved", 2500);
      }
    }
  }

  // Invoices list with filters
  await goto(page, "/invoices?currency=EUR&sort=total_desc");
  await step(page, "6 · Keyword filtering over all extracted invoices (currency, supplier, dates, amounts, status…)", 4500);

  // Search
  await goto(page, "/search");
  const box = page.getByRole("searchbox").or(page.locator('input[type="search"], input[name="q"]')).first();
  await box.fill("cloud hosting and software licences");
  await box.press("Enter");
  await page.waitForLoadState("networkidle");
  await step(page, "7 · Hybrid search: semantic (pgvector embeddings) + full-text, fused with reciprocal rank fusion", 5000);

  // Cross-verify PDF vs Excel
  const docs = await apiJson("/api/documents?page_size=100");
  const left = docs.items.find((d) => d.original_filename.startsWith("batch_march"));
  const erp = docs.items.find((d) => d.original_filename.startsWith("erp_export"));
  await goto(page, "/reconcile");
  await step(page, "8 · Cross-verification: compare a supplier PDF batch against an ERP Excel export", 3500);
  if (left && erp) {
    await page.locator("#recon-left").selectOption(left.id);
    await page.locator("#recon-right").selectOption(erp.id);
    await page.getByRole("button", { name: /run|compare|verify/i }).first().click();
    await page.waitForLoadState("networkidle");
    await pause(1500);
    await step(page, "Matched, mismatched (field by field) and missing invoices on either side", 6000);
  }

  await goto(page, "/");
  await step(page, "API docs: http://localhost:8000/docs · Tests, evaluation report and architecture in /docs", 4000);

  await context.close();
  await browser.close();
  const [video] = readdirSync(tmpVideo).filter((f) => f.endsWith(".webm"));
  renameSync(path.join(tmpVideo, video), path.join(outDir, "walkthrough.webm"));
  rmSync(tmpVideo, { recursive: true, force: true });
  console.log("saved", path.join(outDir, "walkthrough.webm"));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
