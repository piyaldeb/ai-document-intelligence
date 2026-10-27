---
title: DocIntel — AI Document Intelligence
emoji: 📄
colorFrom: blue
colorTo: yellow
sdk: docker
app_port: 7860
pinned: true
short_description: Extract, validate and cross-verify invoices from PDFs & sheets
---

# DocIntel: live demo

AI document intelligence for invoices, receipts, scanned PDFs, photos and spreadsheets. It extracts structured data with OCR and AI, validates it (arithmetic, duplicates, missing fields), lets people review and correct it with an audit trail, cross-verifies PDF vs Excel, and searches with keyword, semantic and hybrid search.

**Source code, architecture, tests and evaluation report:** https://github.com/piyaldeb/ai-document-intelligence

## Try it in two minutes
1. **Dashboard:** sample documents are already processed. Drag in your own PDF/JPG/PNG/TIFF/XLSX/XLS/CSV files, or [download samples](https://github.com/piyaldeb/ai-document-intelligence/tree/main/eval/dataset), and watch the live progress.
2. **Review queue:** open a flagged invoice, e.g. `total_mismatch.pdf`. Each field shows its confidence and the evidence it came from, and the validation issues are listed. Correct a value, save (it is re-validated and audited), then approve.
3. **Search:** try "cloud hosting" (semantic) or an invoice number (keyword).
4. **Cross-verify:** compare `batch_march_20_invoices.pdf` with `erp_export_march.xlsx` to see the planted mismatches and missing invoices.
5. **API docs:** `/api/docs` (Swagger; requests go through the app's proxy).

## About this demo
* All sample data is **synthetic**. Don't upload confidential documents: this instance is public, and its data resets every 24 h.
* Extraction runs on the built-in rules engine. The Claude LLM path is disabled here to avoid public API costs.
* It runs all services (PostgreSQL + pgvector, Redis, FastAPI, Celery, Next.js) in one container on free CPU hardware, so OCR is slower than on the multi-container deployment. The Space sleeps when idle; the first visit wakes it in about a minute.
* This is a technical-assessment project built with AI assistance. See the repository's DISCLAIMER and AI disclosure.
