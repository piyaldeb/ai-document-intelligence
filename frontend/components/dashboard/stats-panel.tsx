"use client";

import Link from "next/link";
import { Bot, Clock, FileText, Receipt, Wallet, TriangleAlert } from "lucide-react";
import { Badge, Card, CardHeader, EmptyState, ErrorState, Stat, cn } from "@/components/ui";
import { formatDuration, formatMoney, formatNumber } from "@/lib/format";
import { DOCUMENT_STATUSES, DOCUMENT_STATUS_LABELS, issueLabel, providerLabel } from "@/lib/labels";
import type { Stats } from "@/lib/types";

const STATUS_DOT: Record<string, string> = {
  queued: "bg-slate-400",
  processing: "bg-blue-600",
  completed: "bg-emerald-600",
  needs_review: "bg-accent",
  failed: "bg-red-600",
};

function SkeletonCard() {
  return (
    <div className="card animate-pulse p-4" aria-hidden>
      <div className="h-3 w-24 rounded bg-slate-200" />
      <div className="mt-3 h-7 w-16 rounded bg-slate-200" />
      <div className="mt-3 h-3 w-32 rounded bg-slate-100" />
    </div>
  );
}

export function StatCards({ stats, error, onRetry }: { stats?: Stats; error: Error | null; onRetry: () => void }) {
  if (error && !stats) {
    return (
      <Card className="mb-6">
        <ErrorState title="Could not load statistics" error={error} onRetry={onRetry} />
      </Card>
    );
  }
  if (!stats) {
    return (
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" role="status" aria-label="Loading statistics">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }
  const docs = stats.documents;
  const inv = stats.invoices;
  const provider = stats.extraction_provider;
  return (
    <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Stat
        label="Documents"
        value={formatNumber(docs.total ?? 0)}
        icon={<FileText className="size-4" aria-hidden />}
        hint={
          <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
            {DOCUMENT_STATUSES.map((s) => (
              <li key={s} className="inline-flex items-center gap-1.5">
                <span className={cn("size-2 rounded-full", STATUS_DOT[s])} aria-hidden />
                {DOCUMENT_STATUS_LABELS[s]} <span className="font-semibold text-ink">{formatNumber(docs[s] ?? 0)}</span>
              </li>
            ))}
          </ul>
        }
      />
      <Stat
        label="Invoices"
        value={formatNumber(inv.total ?? 0)}
        icon={<Receipt className="size-4" aria-hidden />}
        accent={(inv.needs_review ?? 0) > 0}
        hint={
          <span className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
            <Link href="/review" className="link inline-flex items-center gap-1">
              <TriangleAlert className="size-3 text-accent-strong" aria-hidden />
              {formatNumber(inv.needs_review ?? 0)} need review
            </Link>
            <span>
              <span className="font-semibold text-ink">{formatNumber(inv.approved ?? 0)}</span> approved
            </span>
            <span>
              <span className="font-semibold text-ink">{formatNumber(inv.ok ?? 0)}</span> auto-validated
            </span>
          </span>
        }
      />
      <Stat
        label="Avg processing time"
        value={formatDuration(stats.avg_processing_ms)}
        icon={<Clock className="size-4" aria-hidden />}
        hint="Per document, upload to searchable"
      />
      <Stat
        label="Extraction engine"
        value={
          <Badge tone={provider === "anthropic" ? "navy" : "grey"} className="px-2.5 py-1 text-sm">
            {providerLabel(provider)}
          </Badge>
        }
        icon={<Bot className="size-4" aria-hidden />}
        hint={
          provider === "anthropic"
            ? "Schema-constrained LLM extraction, grounded against the source text"
            : "Deterministic rules extractor (no LLM key configured)"
        }
      />
    </div>
  );
}

export function CurrencyTotals({ stats }: { stats?: Stats }) {
  const entries = Object.entries(stats?.total_amount_by_currency ?? {}).sort((a, b) => b[1] - a[1]);
  return (
    <Card>
      <CardHeader title="Totals by currency" description="Sum of extracted invoice totals" />
      {!stats ? (
        <div className="space-y-2 p-4" aria-hidden>
          <div className="h-4 w-3/4 animate-pulse rounded bg-slate-100" />
          <div className="h-4 w-1/2 animate-pulse rounded bg-slate-100" />
        </div>
      ) : entries.length === 0 ? (
        <EmptyState icon={<Wallet className="size-5" aria-hidden />} title="No invoices yet" className="py-8" />
      ) : (
        <ul className="divide-y divide-line">
          {entries.map(([cur, amount]) => (
            <li key={cur} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm sm:px-5">
              <span className="font-semibold text-muted">{cur === "unknown" ? "No currency" : cur}</span>
              <span className="font-heading font-semibold text-primary-dark tabular-nums">
                {formatMoney(amount, cur === "unknown" ? null : cur)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function TopIssues({ stats }: { stats?: Stats }) {
  const entries = Object.entries(stats?.issues_by_code ?? {});
  return (
    <Card>
      <CardHeader title="Top validation issues" description="Errors and warnings across all invoices" />
      {!stats ? (
        <div className="space-y-2 p-4" aria-hidden>
          <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
          <div className="h-4 w-1/2 animate-pulse rounded bg-slate-100" />
        </div>
      ) : entries.length === 0 ? (
        <EmptyState title="No open issues" description="Validation errors and warnings will be listed here." className="py-8" />
      ) : (
        <ul className="divide-y divide-line">
          {entries.slice(0, 8).map(([code, count]) => (
            <li key={code}>
              <Link
                href={`/invoices?issue_code=${encodeURIComponent(code)}`}
                className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm hover:bg-primary-50/60 sm:px-5"
              >
                <span className="min-w-0">
                  <span className="block font-medium text-primary">{issueLabel(code)}</span>
                  <span className="block font-mono text-[0.7rem] text-muted">{code}</span>
                </span>
                <Badge tone="amber">{formatNumber(count)}</Badge>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
