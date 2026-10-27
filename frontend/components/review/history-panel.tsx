import { Activity, ArrowRight } from "lucide-react";
import { formatDate, formatDateTime } from "@/lib/format";
import { REVIEW_STATUS_LABELS, fieldLabel } from "@/lib/labels";
import type { CorrectionOut, ReviewStatus } from "@/lib/types";
import { Card, EmptyState } from "@/components/ui";

function describe(field: string, v: unknown): string {
  if (v === null || v === undefined || v === "") return "(empty)";
  if (field === "review_status" && typeof v === "string") return REVIEW_STATUS_LABELS[v as ReviewStatus] ?? v;
  if (field === "invoice_date" && typeof v === "string") return formatDate(v);
  if (Array.isArray(v)) return `${v.length} line item${v.length === 1 ? "" : "s"}`;
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

type LineSnapshot = { description?: string | null; quantity?: unknown; unit_price?: unknown; amount?: unknown };

function LineItemsDiff({ value }: { value: unknown }) {
  if (!Array.isArray(value) || !value.length) return null;
  return (
    <details className="mt-1 text-xs">
      <summary className="cursor-pointer text-primary hover:underline">Show new line items</summary>
      <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-muted">
        {(value as LineSnapshot[]).map((li, i) => (
          <li key={i} className="break-words">
            {li.description || "(no description)"} — {String(li.quantity ?? "?")} × {String(li.unit_price ?? "?")} ={" "}
            <span className="font-mono text-ink">{String(li.amount ?? "?")}</span>
          </li>
        ))}
      </ol>
    </details>
  );
}

export function HistoryPanel({ corrections }: { corrections: CorrectionOut[] }) {
  const list = [...corrections].sort((a, b) => b.id - a.id);
  return (
    <Card aria-labelledby="history-title">
      <div className="border-b border-line px-4 py-3">
        <h2 id="history-title" className="text-base font-semibold">
          Correction history
        </h2>
        <p className="mt-0.5 text-xs text-muted">Audit trail of every manual change and approval</p>
      </div>
      {list.length === 0 ? (
        <EmptyState icon={<Activity className="size-5" aria-hidden />} title="No corrections yet" className="py-8" />
      ) : (
        <ol className="divide-y divide-line">
          {list.map((c) => (
            <li key={c.id} className="px-4 py-3 text-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-x-2">
                <span className="font-semibold text-ink">{fieldLabel(c.field)}</span>
                <time className="text-xs text-muted" dateTime={c.created_at}>
                  {formatDateTime(c.created_at)}
                </time>
              </div>
              <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
                <span className="rounded bg-red-50 px-1.5 py-0.5 break-all text-red-900 line-through decoration-red-400/70">
                  {describe(c.field, c.old_value)}
                </span>
                <ArrowRight className="size-3 text-muted" aria-label="changed to" />
                <span className="rounded bg-emerald-50 px-1.5 py-0.5 font-medium break-all text-emerald-900">
                  {describe(c.field, c.new_value)}
                </span>
              </p>
              {c.field === "line_items" && <LineItemsDiff value={c.new_value} />}
              {(c.reason || c.corrected_by) && (
                <p className="mt-1 text-xs text-muted">
                  {c.reason && <span className="italic">“{c.reason}”</span>}
                  {c.reason && c.corrected_by && " — "}
                  {c.corrected_by && <span>by {c.corrected_by}</span>}
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
