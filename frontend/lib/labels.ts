import type { DocumentStatus, ReviewStatus } from "./types";

export const ACCEPTED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".xlsx", ".xls", ".csv"] as const;
export const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",");

export function extensionOf(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

export function isAcceptedFile(name: string): boolean {
  return (ACCEPTED_EXTENSIONS as readonly string[]).includes(extensionOf(name));
}

export const DOCUMENT_STATUSES: DocumentStatus[] = ["queued", "processing", "completed", "needs_review", "failed"];
export const ACTIVE_STATUSES: DocumentStatus[] = ["queued", "processing"];

export function isActive(status: string | null | undefined): boolean {
  return status === "queued" || status === "processing";
}

export const DOCUMENT_STATUS_LABELS: Record<DocumentStatus, string> = {
  queued: "Queued",
  processing: "Processing",
  completed: "Completed",
  needs_review: "Needs review",
  failed: "Failed",
};

export const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  ok: "OK",
  needs_review: "Needs review",
  approved: "Approved",
};

/** Pipeline stages from backend/app/pipeline/processor.py. */
export const STAGE_LABELS: Record<string, string> = {
  queued: "Waiting in queue",
  detect: "Detecting file type",
  extract_text: "Extracting text",
  segment: "Splitting into invoices",
  ai_extraction: "Extracting fields",
  validate: "Validating",
  index: "Indexing for search",
  done: "Done",
  failed: "Failed",
  finalize: "Finalizing",
};

export function stageLabel(stage: string | null | undefined): string {
  if (!stage) return "—";
  return STAGE_LABELS[stage] ?? stage.replace(/_/g, " ");
}

export const FILE_TYPE_LABELS: Record<string, string> = {
  pdf: "PDF",
  image: "Image",
  xlsx: "Excel",
  xls: "Excel (xls)",
  csv: "CSV",
};

export function fileTypeLabel(t: string | null | undefined): string {
  if (!t) return "—";
  return FILE_TYPE_LABELS[t] ?? t.toUpperCase();
}

export function isSpreadsheet(t: string | null | undefined): boolean {
  return t === "xlsx" || t === "xls" || t === "csv";
}

/** Invoice fields (backend/app/validation/rules.py::FIELD_LABELS). */
export const FIELD_LABELS: Record<string, string> = {
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  supplier_name: "Supplier",
  customer_name: "Customer",
  subtotal: "Subtotal",
  tax: "Tax",
  total: "Total",
  currency: "Currency",
  line_items: "Line items",
  line_items_count: "Line item count",
  review_status: "Review status",
};

export function fieldLabel(f: string | null | undefined): string {
  if (!f) return "Document";
  return FIELD_LABELS[f] ?? f.replace(/_/g, " ");
}

/** Validation issue codes (backend/app/validation/rules.py). */
export const ISSUE_CODES: Record<string, string> = {
  MISSING_FIELD: "Missing field",
  NEGATIVE_AMOUNT: "Negative amount",
  IMPLAUSIBLE_AMOUNT: "Implausible amount",
  ZERO_TOTAL: "Zero total",
  UNUSUAL_TAX_RATE: "Unusual tax rate",
  SUBTOTAL_EXCEEDS_TOTAL: "Subtotal exceeds total",
  INVALID_NUMBER: "Invalid number",
  TOTAL_MISMATCH: "Total mismatch",
  LINE_ITEMS_MISMATCH: "Line items mismatch",
  LINE_ITEM_INCOMPLETE: "Incomplete line items",
  LINE_ITEM_MATH: "Line item math",
  NO_LINE_ITEMS: "No line items",
  FUTURE_DATE: "Future date",
  OLD_DATE: "Old date",
  AMBIGUOUS_DATE: "Ambiguous date",
  INVALID_DATE: "Invalid date",
  UNKNOWN_CURRENCY: "Unknown currency",
  DUPLICATE_INVOICE: "Duplicate invoice",
  POSSIBLE_DUPLICATE: "Possible duplicate",
  LOW_CONFIDENCE: "Low confidence",
  UNGROUNDED_VALUE: "Ungrounded value",
  LOW_OCR_QUALITY: "Low OCR quality",
};

export function issueLabel(code: string): string {
  return ISSUE_CODES[code] ?? code.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());
}

export const PAGE_METHOD_LABELS: Record<string, string> = {
  text_layer: "Text layer",
  ocr: "OCR",
  spreadsheet: "Spreadsheet",
};

export function methodLabel(m: string | null | undefined): string {
  if (!m) return "—";
  return PAGE_METHOD_LABELS[m] ?? m.replace(/_/g, " ");
}

export const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Claude (LLM)",
  rules: "Rules engine",
  auto: "Auto",
};

export function providerLabel(p: string | null | undefined): string {
  if (!p) return "—";
  return PROVIDER_LABELS[p] ?? p;
}

export const RECON_STATUS_LABELS: Record<string, string> = {
  matched: "Matched",
  mismatch: "Mismatch",
  missing_in_left: "Missing in left",
  missing_in_right: "Missing in right",
};
