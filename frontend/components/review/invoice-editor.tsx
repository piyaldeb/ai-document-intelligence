"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { CircleAlert, Plus, Quote, Save, ShieldCheck, TriangleAlert, Undo2, X } from "lucide-react";
import { ApiError, api, errorMessage } from "@/lib/api";
import { useLocalStorage } from "@/lib/hooks";
import { formatDateTime, formatMoney } from "@/lib/format";
import {
  AMOUNT_FIELDS,
  REQUIRED_FIELDS,
  SCALAR_FIELDS,
  amountsClose,
  buildCorrection,
  changedFields,
  cleanNumber,
  emptyLine,
  fieldChanged,
  linesChanged,
  parseNumber,
  round2,
  toForm,
  toLines,
  validateField,
  validateLine,
  type FormValues,
  type LineDraft,
  type ScalarField,
} from "@/lib/invoice-form";
import { fieldLabel } from "@/lib/labels";
import type { InvoiceDetail, IssueOut } from "@/lib/types";
import { ConfidenceBadge, ReviewBadge } from "@/components/badges";
import { useToast } from "@/components/toast";
import { Alert, Button, Card, CardHeader, TableWrap, cn } from "@/components/ui";
import { HistoryPanel } from "./history-panel";
import { IssuesPanel } from "./issues-panel";

const COMMON_CURRENCIES = ["USD", "EUR", "GBP", "BDT", "INR", "JPY", "CNY", "AUD", "CAD", "CHF", "SGD", "AED"];

function worstSeverity(issues: IssueOut[]): "error" | "warning" | "info" | null {
  if (issues.some((i) => i.severity === "error")) return "error";
  if (issues.some((i) => i.severity === "warning")) return "warning";
  if (issues.length) return "info";
  return null;
}

function focusField(field: string) {
  const target =
    field === "line_items" || field === "line_items_count"
      ? document.getElementById("line-items-anchor")
      : document.getElementById(`inv-${field}`);
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.focus({ preventScroll: true });
}

function FieldRow({
  field,
  value,
  initialValue,
  onChange,
  issues,
  clientError,
  serverError,
  confidence,
  verified,
  evidence,
  rejected,
  currency,
}: {
  field: ScalarField;
  value: string;
  initialValue: string;
  onChange: (v: string) => void;
  issues: IssueOut[];
  clientError: string | null;
  serverError?: string;
  confidence: number | undefined;
  verified: boolean;
  evidence?: string;
  rejected?: unknown;
  currency: string;
}) {
  const id = `inv-${field}`;
  const severity = worstSeverity(issues);
  const isAmount = AMOUNT_FIELDS.includes(field);
  const changed = fieldChanged(field, initialValue, value);
  const error = clientError ?? serverError ?? null;
  const describedBy = [
    issues.length ? `${id}-issues` : null,
    error ? `${id}-error` : null,
    evidence ? `${id}-evidence` : null,
  ]
    .filter(Boolean)
    .join(" ");

  const rejectedText = rejected === undefined || rejected === null ? null : String(rejected);
  const rejectedUsable =
    rejectedText !== null &&
    (isAmount
      ? parseNumber(rejectedText) !== null
      : field === "invoice_date"
        ? /^\d{4}-\d{2}-\d{2}$/.test(rejectedText)
        : true);

  return (
    <div
      className={cn(
        "rounded-lg p-3 ring-1 transition-colors",
        severity === "error"
          ? "bg-red-50/50 ring-red-300"
          : severity === "warning"
            ? "bg-amber-50/60 ring-amber-300"
            : "ring-line",
        changed && "border-l-4 border-l-accent",
      )}
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-sm font-semibold text-primary-dark">
          {fieldLabel(field)}
          {REQUIRED_FIELDS.includes(field) && (
            <span className="ml-0.5 text-red-700" aria-hidden>
              *
            </span>
          )}
          {changed && <span className="ml-2 rounded bg-accent-soft px-1.5 py-0.5 text-[0.65rem] font-semibold text-accent-strong uppercase">Edited</span>}
        </label>
        <ConfidenceBadge value={confidence} verified={verified && !changed} />
      </div>
      <div className="relative">
        <input
          id={id}
          name={field}
          type={field === "invoice_date" ? "date" : "text"}
          inputMode={isAmount ? "decimal" : undefined}
          list={field === "currency" ? "currency-codes" : undefined}
          maxLength={field === "currency" ? 3 : field === "invoice_number" ? 64 : 300}
          autoComplete="off"
          spellCheck={false}
          value={value}
          onChange={(e) => onChange(field === "currency" ? e.target.value.toUpperCase() : e.target.value)}
          aria-invalid={error || severity === "error" ? true : undefined}
          aria-describedby={describedBy || undefined}
          aria-required={REQUIRED_FIELDS.includes(field) || undefined}
          className={cn("form-control", isAmount && "pr-14 tabular-nums", field === "currency" && "uppercase")}
          placeholder={isAmount ? "0.00" : field === "currency" ? "USD" : undefined}
        />
        {isAmount && currency && (
          <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs font-semibold text-muted">
            {currency}
          </span>
        )}
      </div>
      {error && (
        <p id={`${id}-error`} className="mt-1 flex items-center gap-1 text-xs font-medium text-red-800">
          <CircleAlert className="size-3" aria-hidden />
          {error}
        </p>
      )}
      {issues.length > 0 && (
        <ul id={`${id}-issues`} className="mt-1.5 space-y-0.5">
          {issues.map((i) => (
            <li
              key={i.id}
              className={cn(
                "flex items-start gap-1 text-xs",
                i.severity === "error" ? "text-red-800" : i.severity === "warning" ? "text-amber-900" : "text-muted",
              )}
            >
              {i.severity === "error" ? (
                <CircleAlert className="mt-0.5 size-3 shrink-0" aria-hidden />
              ) : (
                <TriangleAlert className="mt-0.5 size-3 shrink-0" aria-hidden />
              )}
              <span>
                <span className="sr-only">{i.severity}: </span>
                {i.message}
              </span>
            </li>
          ))}
        </ul>
      )}
      {evidence && (
        <p id={`${id}-evidence`} className="mt-1.5 flex items-start gap-1 text-xs text-muted" title={evidence}>
          <Quote className="mt-0.5 size-3 shrink-0" aria-hidden />
          <span className="line-clamp-2 break-words">
            <span className="sr-only">Evidence from the document: </span>
            {evidence}
          </span>
        </p>
      )}
      {rejectedText !== null && (
        <p className="mt-1.5 flex flex-wrap items-center gap-1.5 rounded bg-amber-50 px-2 py-1 text-xs text-amber-950 ring-1 ring-amber-200">
          <span>
            Discarded unverified value <span className="font-mono font-semibold break-all">“{rejectedText}”</span> (not found in the
            source text)
          </span>
          {rejectedUsable && value !== rejectedText && (
            <button
              type="button"
              className="rounded px-1 font-semibold text-accent-strong underline underline-offset-2 hover:text-ink"
              onClick={() => onChange(isAmount ? cleanNumber(rejectedText) : rejectedText)}
            >
              Use this value
            </button>
          )}
        </p>
      )}
      {changed && (
        <p className="mt-1 text-xs text-muted">
          Was: <span className="font-mono">{initialValue || "(empty)"}</span>
        </p>
      )}
    </div>
  );
}

function LineItemsEditor({
  lines,
  setLines,
  errors,
  currency,
  subtotal,
  tax,
  total,
  issues,
  dirty,
}: {
  lines: LineDraft[];
  setLines: (fn: (prev: LineDraft[]) => LineDraft[]) => void;
  errors: ReturnType<typeof validateLine>[];
  currency: string;
  subtotal: number | null;
  tax: number | null;
  total: number | null;
  issues: IssueOut[];
  dirty: boolean;
}) {
  function update(key: string, patch: Partial<LineDraft>) {
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  }
  const amounts = lines.map((l) => parseNumber(l.amount));
  const nonBlank = lines.filter((l) => l.description.trim() || l.quantity.trim() || l.unit_price.trim() || l.amount.trim());
  const allAmounts = nonBlank.length > 0 && nonBlank.every((l) => parseNumber(l.amount) !== null);
  const sum = round2(amounts.reduce<number>((n, a) => n + (a ?? 0), 0));
  const targetField = subtotal !== null ? "subtotal" : total !== null && !tax ? "total" : null;
  const target = targetField === "subtotal" ? subtotal : targetField === "total" ? total : null;
  const sumOk = target === null || !allAmounts ? null : amountsClose(sum, target);

  return (
    <Card aria-labelledby="line-items-title">
      <CardHeader
        id="line-items-title"
        title={
          <span id="line-items-anchor" tabIndex={-1} className="outline-none">
            Line items
            {dirty && (
              <span className="ml-2 rounded bg-accent-soft px-1.5 py-0.5 align-middle text-[0.65rem] font-semibold text-accent-strong uppercase">
                Edited
              </span>
            )}
          </span>
        }
        description="Quantity × unit price is checked against each amount; the sum is checked against the subtotal."
        actions={
          <Button size="sm" onClick={() => setLines((prev) => [...prev, emptyLine()])} icon={<Plus className="size-3.5" aria-hidden />}>
            Add line
          </Button>
        }
      />
      {issues.length > 0 && (
        <ul className="space-y-1 border-b border-line px-4 py-2.5 sm:px-5">
          {issues.map((i) => (
            <li
              key={i.id}
              className={cn("flex items-start gap-1.5 text-xs", i.severity === "error" ? "text-red-800" : i.severity === "warning" ? "text-amber-900" : "text-muted")}
            >
              {i.severity === "error" ? <CircleAlert className="mt-0.5 size-3 shrink-0" aria-hidden /> : <TriangleAlert className="mt-0.5 size-3 shrink-0" aria-hidden />}
              {i.message}
            </li>
          ))}
        </ul>
      )}
      {lines.length === 0 ? (
        <div className="px-5 py-8 text-center text-sm text-muted">
          No line items. Use <span className="font-semibold">Add line</span> to enter them manually.
        </div>
      ) : (
        <TableWrap label="Line items">
          <table className="table-base min-w-[760px]">
            <thead>
              <tr>
                <th scope="col" className="w-10">
                  #
                </th>
                <th scope="col">Description</th>
                <th scope="col" className="w-24 text-right">
                  Qty
                </th>
                <th scope="col" className="w-32 text-right">
                  Unit price
                </th>
                <th scope="col" className="w-32 text-right">
                  Amount
                </th>
                <th scope="col" className="w-36 text-right">
                  Qty × unit
                </th>
                <th scope="col" className="w-10">
                  <span className="sr-only">Remove</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {lines.map((l, i) => {
                const q = parseNumber(l.quantity);
                const u = parseNumber(l.unit_price);
                const a = parseNumber(l.amount);
                const computed = q !== null && u !== null ? round2(q * u) : null;
                const mismatch = computed !== null && a !== null && !amountsClose(computed, a);
                const err = errors[i] ?? {};
                const n = i + 1;
                return (
                  <tr key={l.key} className={mismatch ? "bg-amber-50/60" : undefined}>
                    <td className="pt-4 text-xs text-muted tabular-nums">{n}</td>
                    <td>
                      <input
                        aria-label={`Line ${n} description`}
                        className="form-control"
                        value={l.description}
                        maxLength={2000}
                        onChange={(e) => update(l.key, { description: e.target.value })}
                        aria-invalid={err.description ? true : undefined}
                      />
                    </td>
                    {(["quantity", "unit_price", "amount"] as const).map((k) => (
                      <td key={k}>
                        <input
                          aria-label={`Line ${n} ${k === "unit_price" ? "unit price" : k}`}
                          inputMode="decimal"
                          className="form-control text-right tabular-nums"
                          value={l[k]}
                          onChange={(e) => update(l.key, { [k]: e.target.value })}
                          aria-invalid={err[k] || (k === "amount" && mismatch) ? true : undefined}
                          title={err[k]}
                        />
                        {err[k] && <p className="mt-0.5 text-[0.7rem] text-red-800">{err[k]}</p>}
                      </td>
                    ))}
                    <td className="pt-4 text-right text-xs whitespace-nowrap tabular-nums">
                      {computed === null ? (
                        <span className="text-muted">—</span>
                      ) : mismatch ? (
                        <span className="inline-flex items-center gap-1 font-semibold text-amber-900" title="Quantity × unit price differs from the amount">
                          <TriangleAlert className="size-3" aria-hidden />
                          {formatMoney(computed, currency || null)}
                          <span className="sr-only"> does not match the amount</span>
                        </span>
                      ) : (
                        <span className="text-emerald-800">{formatMoney(computed, currency || null)} ✓</span>
                      )}
                    </td>
                    <td className="pt-3">
                      <button
                        type="button"
                        onClick={() => setLines((prev) => prev.filter((x) => x.key !== l.key))}
                        className="rounded p-1.5 text-muted hover:bg-red-50 hover:text-red-700"
                        aria-label={`Remove line ${n}`}
                      >
                        <X className="size-4" aria-hidden />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </TableWrap>
      )}
      {nonBlank.length > 0 && (
        <div className="flex flex-col gap-1 border-t border-line px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <span className="text-muted">
            Line items total{" "}
            <span className="font-semibold text-ink tabular-nums">
              {allAmounts ? formatMoney(sum, currency || null) : "incomplete (some amounts are empty)"}
            </span>
          </span>
          {sumOk !== null && targetField && target !== null && (
            <span className={cn("inline-flex items-center gap-1 text-xs font-semibold", sumOk ? "text-emerald-800" : "text-red-800")}>
              {sumOk ? (
                <>✓ matches the {targetField}</>
              ) : (
                <>
                  <CircleAlert className="size-3.5" aria-hidden />
                  {targetField} is {formatMoney(target, currency || null)} (difference {formatMoney(round2(target - sum), currency || null)})
                </>
              )}
            </span>
          )}
        </div>
      )}
    </Card>
  );
}

function NotesCard({ invoice }: { invoice: InvoiceDetail }) {
  const raw = invoice.raw_extraction ?? {};
  const notes = Array.isArray(raw.notes) ? raw.notes.filter((n): n is string => typeof n === "string") : [];
  const crossCheck = raw.evidence?._cross_check;
  const rejected = Object.entries(raw.rejected ?? {});
  if (!notes.length && !crossCheck && !rejected.length && !invoice.model) return null;
  return (
    <Card aria-labelledby="notes-title">
      <div className="border-b border-line px-4 py-3">
        <h2 id="notes-title" className="text-base font-semibold">
          Extraction notes
        </h2>
        <p className="mt-0.5 text-xs text-muted">
          Method <span className="font-semibold text-ink">{invoice.extraction_method}</span>
          {invoice.model && (
            <>
              {" "}
              · model <span className="font-mono text-ink">{invoice.model}</span>
            </>
          )}
        </p>
      </div>
      <div className="space-y-3 px-4 py-3 text-sm">
        {notes.length > 0 && (
          <ul className="list-disc space-y-1 pl-5 text-ink marker:text-accent">
            {notes.map((n, i) => (
              <li key={i} className="break-words">
                {n}
              </li>
            ))}
          </ul>
        )}
        {crossCheck && (
          <p className="text-xs text-muted">
            <span className="font-semibold text-ink">Cross-check:</span> {crossCheck}
          </p>
        )}
        {rejected.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-ink">Discarded (ungrounded) values</p>
            <ul className="mt-1 space-y-0.5 text-xs">
              {rejected.map(([f, v]) => (
                <li key={f} className="break-words">
                  <span className="text-muted">{fieldLabel(f)}:</span> <span className="font-mono">{String(v)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}

export function InvoiceEditor({
  invoice,
  onUpdated,
}: {
  invoice: InvoiceDetail;
  onUpdated: (inv: InvoiceDetail) => void;
}) {
  const toast = useToast();
  const [reviewer, setReviewer] = useLocalStorage("docintel.reviewer");
  const [initial] = useState(() => toForm(invoice));
  const [initialLines] = useState(() => toLines(invoice.line_items));
  const [form, setForm] = useState<FormValues>(initial);
  const [lines, setLines] = useState<LineDraft[]>(initialLines);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [approving, setApproving] = useState(false);
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [forcePrompt, setForcePrompt] = useState<string | null>(null);

  const changed = changedFields(initial, form);
  const linesDirty = linesChanged(initialLines, lines);
  const dirty = changed.length > 0 || linesDirty;
  const fieldErrors: Partial<Record<ScalarField, string>> = {};
  for (const f of SCALAR_FIELDS) {
    const e = validateField(f, form[f]);
    if (e) fieldErrors[f] = e;
  }
  const lineErrors = lines.map(validateLine);
  const invalid = Object.keys(fieldErrors).length > 0 || lineErrors.some((e) => Object.keys(e).length > 0);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const raw = invoice.raw_extraction ?? {};
  const evidence = raw.evidence ?? {};
  const rejected = raw.rejected ?? {};
  const verified = new Set(invoice.corrections.map((c) => c.field));
  const issuesFor = (f: string) => invoice.issues.filter((i) => i.field === f);
  const lineIssues = invoice.issues.filter((i) => i.field === "line_items" && i.severity !== "info");
  const currency = /^[A-Za-z]{3}$/.test(form.currency) ? form.currency.toUpperCase() : "";
  const lastApproval = [...invoice.corrections].reverse().find((c) => c.field === "review_status" && c.new_value === "approved");

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!dirty || invalid || saving) return;
    const body = buildCorrection(initial, form, initialLines, lines, { reason, correctedBy: reviewer });
    setSaving(true);
    setServerErrors({});
    try {
      const updated = await api<InvoiceDetail>(`/api/invoices/${invoice.id}`, { method: "PATCH", body });
      onUpdated(updated);
      toast.success(
        "Changes saved and re-validated",
        updated.error_count || updated.warning_count
          ? `${updated.error_count} error(s), ${updated.warning_count} warning(s) remain.`
          : "All validation checks pass.",
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) setServerErrors(err.fieldErrors);
      toast.error("Could not save", errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function approve(force: boolean) {
    setApproving(true);
    try {
      const updated = await api<InvoiceDetail>(`/api/invoices/${invoice.id}/approve`, {
        method: "POST",
        body: { approved_by: reviewer.trim() || null, force },
      });
      setForcePrompt(null);
      onUpdated(updated);
      toast.success(force ? "Approved despite open errors" : "Invoice approved");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && !force) setForcePrompt(err.message);
      else toast.error("Could not approve", errorMessage(err));
    } finally {
      setApproving(false);
    }
  }

  function discard() {
    setForm(initial);
    setLines(initialLines);
    setReason("");
    setServerErrors({});
  }

  const changeCount = changed.length + (linesDirty ? 1 : 0);
  const pairs: [ScalarField, ScalarField][] = [
    ["invoice_number", "invoice_date"],
    ["supplier_name", "customer_name"],
    ["subtotal", "tax"],
    ["total", "currency"],
  ];

  let reviewBody: ReactNode;
  if (invoice.review_status === "approved") {
    reviewBody = (
      <Alert tone="green" title="Approved">
        {lastApproval ? (
          <>
            {lastApproval.corrected_by ? `by ${lastApproval.corrected_by} ` : ""}on {formatDateTime(lastApproval.created_at)}
            {lastApproval.reason === "forced approval" && " (approved with open errors)"}
          </>
        ) : (
          "This invoice has been approved."
        )}
        <span className="mt-1 block text-xs">Saving a new correction sends it back to review.</span>
      </Alert>
    );
  } else {
    reviewBody = (
      <>
        <Button
          variant="navy"
          className="w-full"
          onClick={() => approve(false)}
          loading={approving && !forcePrompt}
          disabled={dirty || !!forcePrompt}
          title={dirty ? "Save or discard your changes first" : undefined}
          icon={<ShieldCheck className="size-4" aria-hidden />}
        >
          Approve invoice
        </Button>
        {dirty && <p className="mt-1.5 text-xs text-muted">Save or discard your changes before approving.</p>}
        {forcePrompt && (
          <Alert
            tone="amber"
            className="mt-3"
            title="Validation errors remain"
            actions={
              <>
                <Button size="sm" variant="primary" loading={approving} onClick={() => approve(true)}>
                  Approve anyway
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setForcePrompt(null)}>
                  Cancel
                </Button>
              </>
            }
          >
            {forcePrompt} Approving anyway is recorded as a forced approval in the audit trail.
          </Alert>
        )}
      </>
    );
  }

  return (
    <form onSubmit={save} noValidate className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <datalist id="currency-codes">
        {COMMON_CURRENCIES.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>

      <div className="flex min-w-0 flex-col gap-6 lg:col-span-2">
        <Card aria-labelledby="fields-title">
          <CardHeader
            id="fields-title"
            title="Extracted fields"
            description="Confidence badges come from the extractor; the quote under a field is the source evidence."
          />
          <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 sm:p-5">
            {pairs.flat().map((f) => (
              <FieldRow
                key={f}
                field={f}
                value={form[f]}
                initialValue={initial[f]}
                onChange={(v) => setForm((prev) => ({ ...prev, [f]: v }))}
                issues={issuesFor(f)}
                clientError={fieldErrors[f] ?? null}
                serverError={serverErrors[f]}
                confidence={invoice.field_confidence?.[f]}
                verified={verified.has(f)}
                evidence={evidence[f]}
                rejected={f in rejected ? rejected[f] : undefined}
                currency={currency}
              />
            ))}
          </div>
        </Card>

        <LineItemsEditor
          lines={lines}
          setLines={setLines}
          errors={lineErrors}
          currency={currency}
          subtotal={parseNumber(form.subtotal)}
          tax={parseNumber(form.tax)}
          total={parseNumber(form.total)}
          issues={lineIssues}
          dirty={linesDirty}
        />

        <div className={dirty ? "sticky bottom-3 z-20" : undefined}>
          <div
            className={cn(
              "card flex flex-col gap-3 p-3 sm:flex-row sm:items-end",
              dirty ? "border-accent shadow-lg ring-2 ring-accent/30" : "opacity-95",
            )}
          >
            <div className="min-w-0 flex-1">
              <label htmlFor="correction-reason" className="form-label">
                {dirty ? `${changeCount} unsaved change${changeCount === 1 ? "" : "s"}` : "No unsaved changes"} · reason (optional)
              </label>
              <input
                id="correction-reason"
                className="form-control"
                placeholder="e.g. Total corrected from the scanned original"
                maxLength={500}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                disabled={!dirty}
              />
            </div>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={discard} disabled={!dirty || saving} icon={<Undo2 className="size-4" aria-hidden />}>
                Discard
              </Button>
              <Button
                type="submit"
                variant="primary"
                loading={saving}
                disabled={!dirty || invalid}
                title={invalid ? "Fix the highlighted values first" : undefined}
                icon={<Save className="size-4" aria-hidden />}
              >
                Save &amp; re-validate
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="flex min-w-0 flex-col gap-6">
        <Card aria-labelledby="review-title">
          <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
            <h2 id="review-title" className="text-base font-semibold">
              Review
            </h2>
            <ReviewBadge status={invoice.review_status} />
          </div>
          <div className="space-y-3 px-4 py-4">
            <div>
              <label htmlFor="reviewer" className="form-label">
                Your name (for the audit trail)
              </label>
              <input
                id="reviewer"
                className="form-control"
                value={reviewer}
                maxLength={128}
                autoComplete="name"
                placeholder="Optional"
                onChange={(e) => setReviewer(e.target.value)}
              />
            </div>
            {reviewBody}
          </div>
        </Card>

        <IssuesPanel issues={invoice.issues} stale={dirty} onFocusField={focusField} />
        <NotesCard invoice={invoice} />
        <HistoryPanel corrections={invoice.corrections} />
      </div>
    </form>
  );
}
