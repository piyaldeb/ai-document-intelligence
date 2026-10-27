/**
 * TypeScript mirror of backend/app/schemas.py (the API contract).
 * Decimals arrive as JSON numbers, dates as ISO strings, ids as UUID strings.
 */

export type DocumentStatus = "queued" | "processing" | "completed" | "needs_review" | "failed";
export type ReviewStatus = "ok" | "needs_review" | "approved";
export type Severity = "error" | "warning" | "info";
export type FileType = "pdf" | "image" | "xlsx" | "xls" | "csv" | (string & {});
export type PageMethod = "text_layer" | "ocr" | "spreadsheet" | (string & {});
export type SearchMode = "hybrid" | "keyword" | "semantic";
export type ReconStatus = "matched" | "mismatch" | "missing_in_left" | "missing_in_right";

export interface UploadResult {
  filename: string;
  accepted: boolean;
  document_id: string | null;
  duplicate_of: string | null;
  error: string | null;
}

export interface UploadResponse {
  accepted: number;
  rejected: number;
  results: UploadResult[];
}

export interface DocumentSummary {
  id: string;
  original_filename: string;
  file_type: FileType;
  size_bytes: number;
  status: DocumentStatus;
  stage: string | null;
  progress: number;
  page_count: number | null;
  invoice_count: number;
  error_code: string | null;
  error_message: string | null;
  attempts: number;
  duplicate_of_id: string | null;
  extraction_provider: string | null;
  created_at: string;
  processing_started_at: string | null;
  processing_finished_at: string | null;
  processing_ms: number | null;
}

export interface DocumentStatusOut {
  id: string;
  status: DocumentStatus;
  stage: string | null;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  invoice_count: number;
  processing_ms: number | null;
}

export interface PageMeta {
  page_number: number;
  sheet_name: string | null;
  method: PageMethod;
  ocr_confidence: number | null;
  char_count: number;
  warnings: string[];
}

export interface PageOut extends PageMeta {
  text: string;
}

export interface EventOut {
  id: number;
  attempt: number;
  stage: string;
  status: "started" | "completed" | "failed" | "info" | (string & {});
  message: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface IssueOut {
  id: number;
  invoice_id: string | null;
  code: string;
  severity: Severity;
  field: string | null;
  message: string;
  details: Record<string, unknown>;
}

export interface LineItemOut {
  id: number;
  position: number;
  description: string | null;
  quantity: number | null;
  unit_price: number | null;
  amount: number | null;
}

export interface CorrectionOut {
  id: number;
  field: string;
  old_value: unknown;
  new_value: unknown;
  reason: string | null;
  corrected_by: string | null;
  created_at: string;
}

export interface SourceRef {
  pages?: number[];
  sheet?: string;
  rows?: [number, number];
  [key: string]: unknown;
}

export interface InvoiceSummary {
  id: string;
  document_id: string;
  sequence: number;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  customer_name: string | null;
  subtotal: number | null;
  tax: number | null;
  total: number | null;
  currency: string | null;
  review_status: ReviewStatus;
  needs_review: boolean;
  error_count: number;
  warning_count: number;
  extraction_method: string;
  page_start: number | null;
  page_end: number | null;
  source_ref: SourceRef;
}

/** raw_extraction is the extractor's JSON dump (InvoiceData minus line items). */
export interface RawExtraction {
  evidence?: Record<string, string>;
  rejected?: Record<string, unknown>;
  notes?: string[];
  confidence?: Record<string, number>;
  method?: string;
  model?: string | null;
  ambiguous_date?: boolean;
  date_corrected?: boolean;
  min_ocr_confidence?: number | null;
  [key: string]: unknown;
}

export interface InvoiceDetail extends InvoiceSummary {
  document_name: string | null;
  field_confidence: Record<string, number>;
  model: string | null;
  raw_extraction: RawExtraction;
  source_text: string;
  line_items: LineItemOut[];
  issues: IssueOut[];
  corrections: CorrectionOut[];
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  sha256: string;
  mime_type: string;
  meta: Record<string, unknown>;
  pages: PageMeta[];
  invoices: InvoiceSummary[];
  events: EventOut[];
  issues: IssueOut[];
}

export interface PageInfo {
  total: number;
  page: number;
  page_size: number;
}

export interface DocumentList {
  items: DocumentSummary[];
  meta: PageInfo;
}

export interface InvoiceList {
  items: InvoiceSummary[];
  meta: PageInfo;
}

export type Decimalish = string | number | null;

export interface LineItemIn {
  description: string | null;
  quantity: Decimalish;
  unit_price: Decimalish;
  amount: Decimalish;
}

/** PATCH body: send only the fields that changed (null clears a value). Extra keys -> 422. */
export interface InvoiceCorrection {
  invoice_number?: string | null;
  invoice_date?: string | null;
  supplier_name?: string | null;
  customer_name?: string | null;
  subtotal?: Decimalish;
  tax?: Decimalish;
  total?: Decimalish;
  currency?: string | null;
  line_items?: LineItemIn[];
  reason?: string | null;
  corrected_by?: string | null;
}

export interface ApproveRequest {
  approved_by?: string | null;
  force?: boolean;
}

/** The compact invoice dict embedded in search hits (search/service.py::_invoice_summary). */
export interface SearchInvoice {
  id: string;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  customer_name: string | null;
  total: number | null;
  currency: string | null;
  review_status: ReviewStatus;
}

export interface SearchHit {
  document_id: string;
  document_name: string;
  invoice_id: string | null;
  page_number: number | null;
  snippet: string;
  score: number;
  match: "keyword" | "semantic" | "hybrid" | (string & {});
  sources: string[];
  invoice: SearchInvoice | null;
}

export interface SearchResponse {
  query: string;
  mode: SearchMode;
  took_ms: number;
  results: SearchHit[];
}

export interface ReprocessResponse {
  queued: string[];
}

export interface ReconcileRequest {
  left_document_id: string;
  right_document_id: string;
  amount_tolerance: number;
}

export interface Difference {
  field: string;
  left: unknown;
  right: unknown;
}

export interface ReconciliationItem {
  id: number;
  match_key: string | null;
  status: ReconStatus;
  left_invoice_id: string | null;
  right_invoice_id: string | null;
  differences: Difference[];
  left: InvoiceSummary | null;
  right: InvoiceSummary | null;
}

export interface ReconciliationSummary {
  left_invoices?: number;
  right_invoices?: number;
  matched?: number;
  mismatch?: number;
  missing_in_left?: number;
  missing_in_right?: number;
  mismatched_fields?: Record<string, number>;
  [key: string]: unknown;
}

export interface Reconciliation {
  id: string;
  left_document_id: string;
  right_document_id: string;
  left_document_name: string | null;
  right_document_name: string | null;
  summary: ReconciliationSummary;
  params: { tolerance?: string; [key: string]: unknown };
  created_at: string;
  items: ReconciliationItem[];
}

export interface Stats {
  documents: Record<string, number>;
  invoices: Record<string, number>;
  issues_by_code: Record<string, number>;
  avg_processing_ms: number | null;
  total_amount_by_currency: Record<string, number>;
  extraction_provider: string;
}

export interface Health {
  status: string;
  extraction_provider: string;
}
