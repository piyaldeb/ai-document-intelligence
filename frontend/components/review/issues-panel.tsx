"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronDown, CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import { fieldLabel, issueLabel } from "@/lib/labels";
import type { IssueOut, Severity } from "@/lib/types";
import { Card, cn } from "@/components/ui";

const GROUPS: { severity: Severity; title: string; icon: typeof CircleAlert; tone: string; headTone: string }[] = [
  { severity: "error", title: "Errors", icon: CircleAlert, tone: "text-red-700", headTone: "text-red-900" },
  { severity: "warning", title: "Warnings", icon: TriangleAlert, tone: "text-amber-700", headTone: "text-amber-950" },
  { severity: "info", title: "Info", icon: Info, tone: "text-slate-500", headTone: "text-slate-700" },
];

const DETAIL_LABELS: Record<string, string> = {
  expected: "Expected",
  actual: "Actual",
  difference: "Difference",
  line: "Line",
  rate: "Rate",
  confidence: "Confidence",
  rejected_value: "Discarded value",
  raw: "Raw value",
  line_items_sum: "Line items sum",
  subtotal: "Subtotal",
  total: "Total",
  ocr_confidence: "OCR confidence",
};

function IssueDetails({ issue }: { issue: IssueOut }) {
  const d = issue.details ?? {};
  const otherInvoice = typeof d.invoice_id === "string" ? d.invoice_id : null;
  const entries = Object.entries(d).filter(
    ([k, v]) =>
      !["invoice_id", "document_id", "document_name", "invoice_number"].includes(k) &&
      (typeof v === "string" || typeof v === "number"),
  );
  if (!otherInvoice && !entries.length) return null;
  return (
    <div className="mt-1 space-y-0.5 text-xs text-muted">
      {entries.length > 0 && (
        <p className="flex flex-wrap gap-x-3">
          {entries.map(([k, v]) => (
            <span key={k}>
              {DETAIL_LABELS[k] ?? k.replace(/_/g, " ")}:{" "}
              <span className="font-mono text-ink">
                {k === "rate" && typeof v === "number" ? `${(v * 100).toFixed(1)}%` : k === "confidence" && typeof v === "number" ? `${Math.round(v * 100)}%` : String(v)}
              </span>
            </span>
          ))}
        </p>
      )}
      {otherInvoice && (
        <p>
          <Link href={`/invoices/${otherInvoice}`} className="link">
            Open {typeof d.invoice_number === "string" ? `invoice ${d.invoice_number}` : "the other invoice"}
          </Link>
          {typeof d.document_name === "string" && <> in {d.document_name}</>}
        </p>
      )}
    </div>
  );
}

export function IssuesPanel({
  issues,
  stale,
  onFocusField,
}: {
  issues: IssueOut[];
  stale: boolean;
  onFocusField: (field: string) => void;
}) {
  const [showInfo, setShowInfo] = useState(false);
  const counts = { error: 0, warning: 0, info: 0 } as Record<Severity, number>;
  for (const i of issues) counts[i.severity] = (counts[i.severity] ?? 0) + 1;

  return (
    <Card aria-labelledby="issues-title">
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <h2 id="issues-title" className="text-base font-semibold">
          Validation
        </h2>
        <span className="text-xs text-muted">
          {counts.error} {counts.error === 1 ? "error" : "errors"} · {counts.warning} {counts.warning === 1 ? "warning" : "warnings"}
        </span>
      </div>
      {stale && (
        <p className="border-b border-line bg-accent-soft px-4 py-2 text-xs text-amber-950">
          You have unsaved edits. Issues reflect the last saved version and are re-checked when you save.
        </p>
      )}
      {counts.error + counts.warning === 0 && (
        <div className="flex items-center gap-2 px-4 py-4 text-sm text-emerald-900">
          <CircleCheck className="size-4 text-emerald-700" aria-hidden />
          All validation checks passed.
        </div>
      )}
      {GROUPS.map((g) => {
        const list = issues.filter((i) => i.severity === g.severity);
        if (!list.length) return null;
        const collapsed = g.severity === "info" && !showInfo;
        return (
          <section key={g.severity} aria-label={g.title} className="border-b border-line last:border-b-0">
            {g.severity === "info" ? (
              <button
                type="button"
                className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-semibold text-slate-700 hover:bg-slate-50"
                aria-expanded={!collapsed}
                onClick={() => setShowInfo((s) => !s)}
              >
                <span className="flex items-center gap-2">
                  <Info className="size-4 text-slate-500" aria-hidden />
                  {g.title} ({list.length})
                </span>
                <ChevronDown className={cn("size-4 transition-transform", !collapsed && "rotate-180")} aria-hidden />
              </button>
            ) : (
              <h3 className={cn("flex items-center gap-2 px-4 pt-3 text-sm font-semibold", g.headTone)}>
                <g.icon className={cn("size-4", g.tone)} aria-hidden />
                {g.title} ({list.length})
              </h3>
            )}
            {!collapsed && (
              <ul className="space-y-2 px-4 pt-2 pb-3">
                {list.map((issue) => (
                  <li key={issue.id} className="text-sm">
                    <p className="text-ink">{issue.message}</p>
                    <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
                      <span className="font-mono">{issue.code}</span>
                      <span aria-hidden>·</span>
                      <span>{issueLabel(issue.code)}</span>
                      {issue.field && (
                        <>
                          <span aria-hidden>·</span>
                          <button
                            type="button"
                            className="rounded font-medium text-primary underline-offset-2 hover:underline"
                            onClick={() => onFocusField(issue.field!)}
                          >
                            Go to {fieldLabel(issue.field).toLowerCase()}
                          </button>
                        </>
                      )}
                    </p>
                    <IssueDetails issue={issue} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </Card>
  );
}
