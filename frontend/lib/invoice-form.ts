/**
 * Pure helpers for the invoice correction form: server value <-> form string conversion,
 * client-side validation mirroring backend constraints, change detection and the PATCH body
 * (only changed fields are sent; InvoiceCorrection forbids extra keys).
 */
import type { InvoiceCorrection, InvoiceDetail, LineItemIn, LineItemOut } from "./types";

export const SCALAR_FIELDS = [
  "invoice_number",
  "invoice_date",
  "supplier_name",
  "customer_name",
  "subtotal",
  "tax",
  "total",
  "currency",
] as const;
export type ScalarField = (typeof SCALAR_FIELDS)[number];
export const AMOUNT_FIELDS: ScalarField[] = ["subtotal", "tax", "total"];
export const REQUIRED_FIELDS: ScalarField[] = ["invoice_number", "invoice_date", "supplier_name", "total"];

export type FormValues = Record<ScalarField, string>;

export interface LineDraft {
  key: string;
  description: string;
  quantity: string;
  unit_price: string;
  amount: string;
}

const MAX_LEN: Partial<Record<ScalarField, number>> = { invoice_number: 64, supplier_name: 300, customer_name: 300 };

let lineCounter = 0;
export function newLineKey(): string {
  lineCounter += 1;
  return `line-${lineCounter}`;
}

function amountString(v: number | null | undefined): string {
  return v === null || v === undefined ? "" : v.toFixed(2);
}

function plainNumberString(v: number | null | undefined): string {
  if (v === null || v === undefined) return "";
  // Up to 4 decimals (Numeric(18,4)), without trailing zeros.
  return String(Number(v.toFixed(4)));
}

export function toForm(inv: InvoiceDetail): FormValues {
  return {
    invoice_number: inv.invoice_number ?? "",
    invoice_date: inv.invoice_date ?? "",
    supplier_name: inv.supplier_name ?? "",
    customer_name: inv.customer_name ?? "",
    subtotal: amountString(inv.subtotal),
    tax: amountString(inv.tax),
    total: amountString(inv.total),
    currency: inv.currency ?? "",
  };
}

export function toLines(items: LineItemOut[]): LineDraft[] {
  return [...items]
    .sort((a, b) => a.position - b.position)
    .map((li) => ({
      key: newLineKey(),
      description: li.description ?? "",
      quantity: plainNumberString(li.quantity),
      unit_price: plainNumberString(li.unit_price),
      amount: amountString(li.amount),
    }));
}

export function emptyLine(): LineDraft {
  return { key: newLineKey(), description: "", quantity: "", unit_price: "", amount: "" };
}

/** "1,234.50 " -> "1234.50"; returns "" for blank input. */
export function cleanNumber(raw: string): string {
  return raw.replace(/[\s,]/g, "");
}

export function parseNumber(raw: string): number | null {
  const s = cleanNumber(raw);
  if (!s) return null;
  if (!/^-?(\d+(\.\d*)?|\.\d+)$/.test(s)) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

const AMOUNT_RE = /^-?\d{1,14}(\.\d{1,2})?$/;
const DECIMAL_RE = /^-?\d{1,14}(\.\d{1,4})?$/;

export function validateField(field: ScalarField, raw: string): string | null {
  const v = raw.trim();
  if (!v) return null;
  if (AMOUNT_FIELDS.includes(field)) {
    return AMOUNT_RE.test(cleanNumber(v)) ? null : "Enter an amount with at most 2 decimals (e.g. 1250.00)";
  }
  if (field === "currency") return /^[A-Za-z]{3}$/.test(v) ? null : "Use a 3-letter ISO code such as USD or EUR";
  if (field === "invoice_date") return /^\d{4}-\d{2}-\d{2}$/.test(v) ? null : "Enter a valid date";
  const max = MAX_LEN[field];
  if (max && v.length > max) return `At most ${max} characters`;
  return null;
}

export function validateLine(line: LineDraft): Partial<Record<keyof LineDraft, string>> {
  const errs: Partial<Record<keyof LineDraft, string>> = {};
  if (line.description.length > 2000) errs.description = "At most 2000 characters";
  for (const k of ["quantity", "unit_price"] as const) {
    const s = cleanNumber(line[k]);
    if (s && !DECIMAL_RE.test(s)) errs[k] = "Number, up to 4 decimals";
  }
  const a = cleanNumber(line.amount);
  if (a && !AMOUNT_RE.test(a)) errs.amount = "Amount, up to 2 decimals";
  return errs;
}

function normalizedScalar(field: ScalarField, raw: string): string | number | null {
  const v = raw.trim();
  if (!v) return null;
  if (AMOUNT_FIELDS.includes(field)) return parseNumber(v);
  if (field === "currency") return v.toUpperCase();
  return v;
}

export function fieldChanged(field: ScalarField, initial: string, current: string): boolean {
  return normalizedScalar(field, initial) !== normalizedScalar(field, current);
}

export function changedFields(initial: FormValues, current: FormValues): ScalarField[] {
  return SCALAR_FIELDS.filter((f) => fieldChanged(f, initial[f], current[f]));
}

function isBlankLine(l: LineDraft): boolean {
  return !l.description.trim() && !l.quantity.trim() && !l.unit_price.trim() && !l.amount.trim();
}

function lineSignature(lines: LineDraft[]): string {
  return JSON.stringify(
    lines
      .filter((l) => !isBlankLine(l))
      .map((l) => [l.description.trim(), parseNumber(l.quantity), parseNumber(l.unit_price), parseNumber(l.amount)]),
  );
}

export function linesChanged(initial: LineDraft[], current: LineDraft[]): boolean {
  return lineSignature(initial) !== lineSignature(current);
}

function decimalOrNull(raw: string): string | null {
  const s = cleanNumber(raw);
  return s ? s : null;
}

/** Build the PATCH body with only the changed fields (null clears a value). */
export function buildCorrection(
  initial: FormValues,
  current: FormValues,
  initialLines: LineDraft[],
  lines: LineDraft[],
  meta: { reason?: string; correctedBy?: string },
): InvoiceCorrection {
  const body: InvoiceCorrection = {};
  for (const f of changedFields(initial, current)) {
    const v = current[f].trim();
    if (!v) {
      body[f] = null;
    } else if (AMOUNT_FIELDS.includes(f)) {
      body[f as "subtotal" | "tax" | "total"] = cleanNumber(v); // decimal string keeps precision
    } else if (f === "currency") {
      body.currency = v.toUpperCase();
    } else {
      body[f as "invoice_number" | "invoice_date" | "supplier_name" | "customer_name"] = v;
    }
  }
  if (linesChanged(initialLines, lines)) {
    body.line_items = lines
      .filter((l) => !isBlankLine(l))
      .map<LineItemIn>((l) => ({
        description: l.description.trim() || null,
        quantity: decimalOrNull(l.quantity),
        unit_price: decimalOrNull(l.unit_price),
        amount: decimalOrNull(l.amount),
      }));
  }
  if (meta.reason?.trim()) body.reason = meta.reason.trim().slice(0, 500);
  if (meta.correctedBy?.trim()) body.corrected_by = meta.correctedBy.trim().slice(0, 128);
  return body;
}

/** Same tolerance as backend/app/validation/rules.py::_close (abs 0.02 or 0.1 % relative). */
export function amountsClose(a: number, b: number): boolean {
  const tol = Math.max(0.02, Math.abs(b) * 0.001);
  return Math.abs(a - b) <= tol + 1e-9;
}

export function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}
