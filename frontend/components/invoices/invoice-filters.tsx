"use client";

import { useState, type FormEvent } from "react";
import { Funnel, Search, X } from "lucide-react";
import { ISSUE_CODES, FILE_TYPE_LABELS } from "@/lib/labels";
import { Button } from "@/components/ui";

export const INVOICE_FILTER_KEYS = [
  "q",
  "supplier",
  "customer",
  "currency",
  "date_from",
  "date_to",
  "min_total",
  "max_total",
  "review_status",
  "issue_code",
  "file_type",
] as const;
export type InvoiceFilterKey = (typeof INVOICE_FILTER_KEYS)[number];
export type InvoiceFilterValues = Partial<Record<InvoiceFilterKey, string>>;

const ADVANCED: InvoiceFilterKey[] = ["customer", "currency", "date_from", "date_to", "min_total", "max_total", "issue_code", "file_type"];

/**
 * Uncontrolled filter form. The parent remounts it (key = query string) whenever the URL
 * changes, so browser back/forward always shows the filters that produced the results.
 */
export function InvoiceFilters({
  values,
  onApply,
  showReviewStatus = true,
  idPrefix = "f",
}: {
  values: InvoiceFilterValues;
  onApply: (v: InvoiceFilterValues) => void;
  showReviewStatus?: boolean;
  idPrefix?: string;
}) {
  const hasAdvanced = ADVANCED.some((k) => values[k]);
  const [expanded, setExpanded] = useState(hasAdvanced);
  const id = (k: string) => `${idPrefix}-${k}`;

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const out: InvoiceFilterValues = {};
    for (const k of INVOICE_FILTER_KEYS) {
      const v = fd.get(k);
      if (typeof v === "string" && v.trim()) out[k] = k === "currency" ? v.trim().toUpperCase() : v.trim();
    }
    // Hidden (collapsed) advanced fields keep their current values.
    if (!expanded) for (const k of ADVANCED) if (values[k]) out[k] = values[k];
    onApply(out);
  }

  const activeCount = INVOICE_FILTER_KEYS.filter((k) => values[k]).length;

  return (
    <form onSubmit={submit} role="search" aria-label="Filter invoices" className="p-4 sm:p-5">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="sm:col-span-2">
          <label htmlFor={id("q")} className="form-label">
            Keyword
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <input
              id={id("q")}
              name="q"
              type="search"
              defaultValue={values.q}
              placeholder="Invoice number, supplier or customer"
              className="form-control pl-9"
              maxLength={200}
            />
          </div>
        </div>
        <div>
          <label htmlFor={id("supplier")} className="form-label">
            Supplier
          </label>
          <input id={id("supplier")} name="supplier" defaultValue={values.supplier} className="form-control" maxLength={200} />
        </div>
        {showReviewStatus ? (
          <div>
            <label htmlFor={id("review_status")} className="form-label">
              Review status
            </label>
            <select
              id={id("review_status")}
              name="review_status"
              defaultValue={values.review_status ?? ""}
              className="form-control"
              onChange={(e) => e.currentTarget.form?.requestSubmit()}
            >
              <option value="">Any</option>
              <option value="needs_review">Needs review</option>
              <option value="ok">OK</option>
              <option value="approved">Approved</option>
            </select>
          </div>
        ) : (
          <div>
            <label htmlFor={id("issue_code")} className="form-label">
              Issue
            </label>
            <IssueSelect id={id("issue_code")} value={values.issue_code} />
          </div>
        )}
      </div>

      {expanded && (
        <div id={id("advanced")} className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label htmlFor={id("customer")} className="form-label">
              Customer
            </label>
            <input id={id("customer")} name="customer" defaultValue={values.customer} className="form-control" maxLength={200} />
          </div>
          <div>
            <label htmlFor={id("currency")} className="form-label">
              Currency
            </label>
            <input
              id={id("currency")}
              name="currency"
              defaultValue={values.currency}
              className="form-control uppercase"
              maxLength={3}
              pattern="[A-Za-z]{3}"
              title="3-letter ISO code, e.g. USD"
              placeholder="e.g. USD"
              autoComplete="off"
            />
          </div>
          <div>
            <label htmlFor={id("date_from")} className="form-label">
              Date from
            </label>
            <input id={id("date_from")} name="date_from" type="date" defaultValue={values.date_from} className="form-control" />
          </div>
          <div>
            <label htmlFor={id("date_to")} className="form-label">
              Date to
            </label>
            <input id={id("date_to")} name="date_to" type="date" defaultValue={values.date_to} className="form-control" />
          </div>
          <div>
            <label htmlFor={id("min_total")} className="form-label">
              Min total
            </label>
            <input
              id={id("min_total")}
              name="min_total"
              type="number"
              step="0.01"
              inputMode="decimal"
              defaultValue={values.min_total}
              className="form-control"
            />
          </div>
          <div>
            <label htmlFor={id("max_total")} className="form-label">
              Max total
            </label>
            <input
              id={id("max_total")}
              name="max_total"
              type="number"
              step="0.01"
              inputMode="decimal"
              defaultValue={values.max_total}
              className="form-control"
            />
          </div>
          {showReviewStatus && (
            <div>
              <label htmlFor={id("issue_code")} className="form-label">
                Issue
              </label>
              <IssueSelect id={id("issue_code")} value={values.issue_code} />
            </div>
          )}
          <div>
            <label htmlFor={id("file_type")} className="form-label">
              Source file type
            </label>
            <select
              id={id("file_type")}
              name="file_type"
              defaultValue={values.file_type ?? ""}
              className="form-control"
              onChange={(e) => e.currentTarget.form?.requestSubmit()}
            >
              <option value="">Any</option>
              {Object.entries(FILE_TYPE_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button type="submit" variant="primary" icon={<Funnel className="size-4" aria-hidden />}>
          Apply filters
        </Button>
        <Button
          variant="ghost"
          onClick={() => setExpanded((x) => !x)}
          aria-expanded={expanded}
          aria-controls={id("advanced")}
        >
          {expanded ? "Fewer filters" : "More filters"}
        </Button>
        {activeCount > 0 && (
          <Button variant="ghost" onClick={() => onApply({})} icon={<X className="size-4" aria-hidden />}>
            Clear all ({activeCount})
          </Button>
        )}
      </div>
    </form>
  );
}

function IssueSelect({ id, value }: { id: string; value?: string }) {
  return (
    <select
      id={id}
      name="issue_code"
      defaultValue={value ?? ""}
      className="form-control"
      onChange={(e) => e.currentTarget.form?.requestSubmit()}
    >
      <option value="">Any issue</option>
      {Object.entries(ISSUE_CODES).map(([code, label]) => (
        <option key={code} value={code}>
          {label}
        </option>
      ))}
    </select>
  );
}
