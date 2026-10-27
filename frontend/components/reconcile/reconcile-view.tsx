"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ArrowLeftRight, Clock, GitCompareArrows, Play } from "lucide-react";
import { api, errorMessage, qs } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { formatDate, formatDateTime, formatMoney, formatNumber } from "@/lib/format";
import { RECON_STATUS_LABELS, fieldLabel, fileTypeLabel } from "@/lib/labels";
import { isUuid } from "@/lib/ids";
import type { Difference, DocumentList, InvoiceSummary, Reconciliation, ReconciliationItem } from "@/lib/types";
import { ReconStatusBadge } from "@/components/badges";
import { Tabs } from "@/components/controls";
import { useToast } from "@/components/toast";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  TableWrap,
  cn,
} from "@/components/ui";

const AMOUNT_FIELDS = new Set(["subtotal", "tax", "total"]);

function formatDiffValue(field: string, value: unknown, currency: string | null): string {
  if (value === null || value === undefined || value === "") return "(missing)";
  if (AMOUNT_FIELDS.has(field)) return formatMoney(value as string | number, currency);
  if (field === "invoice_date" && typeof value === "string") return formatDate(value);
  return String(value);
}

function InvoiceCell({ inv, fallbackId }: { inv: InvoiceSummary | null; fallbackId: string | null }) {
  if (!inv) {
    return fallbackId ? (
      <Link href={`/invoices/${fallbackId}`} className="link text-xs">
        Open invoice
      </Link>
    ) : (
      <span className="text-xs text-muted italic">Not present</span>
    );
  }
  return (
    <div className="min-w-0">
      <Link href={`/invoices/${inv.id}`} className="link">
        {inv.invoice_number || "No number"}
      </Link>
      <p className="truncate text-xs text-muted" title={inv.supplier_name ?? undefined}>
        {inv.supplier_name || "—"} · {formatDate(inv.invoice_date)}
      </p>
      <p className="text-xs font-semibold text-ink tabular-nums">{formatMoney(inv.total, inv.currency)}</p>
    </div>
  );
}

function Differences({ item }: { item: ReconciliationItem }) {
  if (!item.differences.length) {
    return item.status === "matched" ? (
      <span className="text-xs font-medium text-emerald-800">All compared fields agree</span>
    ) : (
      <span className="text-xs text-muted">—</span>
    );
  }
  return (
    <ul className="space-y-1">
      {item.differences.map((d: Difference, i) => (
        <li key={`${d.field}-${i}`} className="text-xs">
          <span className="font-semibold text-ink">{fieldLabel(d.field)}</span>
          <span className="mt-0.5 flex flex-wrap items-center gap-1">
            <span className="rounded bg-red-50 px-1.5 py-0.5 break-all text-red-900 ring-1 ring-red-200">
              <span className="sr-only">Left: </span>
              {formatDiffValue(d.field, d.left, item.left?.currency ?? null)}
            </span>
            <span aria-hidden className="text-muted">
              ≠
            </span>
            <span className="rounded bg-blue-50 px-1.5 py-0.5 break-all text-blue-900 ring-1 ring-blue-200">
              <span className="sr-only">Right: </span>
              {formatDiffValue(d.field, d.right, item.right?.currency ?? null)}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function SummaryCard({ label, value, tone }: { label: string; value: number; tone: "green" | "red" | "amber" | "navy" }) {
  const styles = {
    green: "border-emerald-200 bg-emerald-50/60 text-emerald-900",
    red: "border-red-200 bg-red-50/60 text-red-900",
    amber: "border-amber-300 bg-amber-50/70 text-amber-950",
    navy: "border-primary-200 bg-primary-50 text-primary-dark",
  }[tone];
  return (
    <div className={cn("rounded-lg border p-3", styles)}>
      <p className="text-xs font-semibold tracking-wide uppercase opacity-80">{label}</p>
      <p className="mt-1 font-heading text-2xl font-semibold tabular-nums">{formatNumber(value)}</p>
    </div>
  );
}

function ResultView({ rec }: { rec: Reconciliation }) {
  const [filter, setFilter] = useState("all");
  const s = rec.summary ?? {};
  const fields = Object.entries(s.mismatched_fields ?? {}).sort((a, b) => b[1] - a[1]);
  const totalFieldDiffs = fields.reduce((n, [, c]) => n + c, 0);
  const items = filter === "all" ? rec.items : rec.items.filter((i) => i.status === filter);
  const count = (st: string) => rec.items.filter((i) => i.status === st).length;

  return (
    <Card aria-labelledby="recon-result">
      <CardHeader
        id="recon-result"
        title="Cross-verification result"
        description={
          <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
            <span className="font-semibold text-ink">Left:</span>
            <Link href={`/documents/${rec.left_document_id}`} className="link break-all">
              {rec.left_document_name ?? "left document"}
            </Link>
            <span className="text-muted">({formatNumber(s.left_invoices ?? 0)} invoices)</span>
            <ArrowLeftRight className="mx-1 size-3.5" aria-label="compared with" />
            <span className="font-semibold text-ink">Right:</span>
            <Link href={`/documents/${rec.right_document_id}`} className="link break-all">
              {rec.right_document_name ?? "right document"}
            </Link>
            <span className="text-muted">({formatNumber(s.right_invoices ?? 0)} invoices)</span>
          </span>
        }
        actions={
          <span className="text-xs text-muted">
            Tolerance {rec.params?.tolerance ?? "0.01"} · {formatDateTime(rec.created_at)}
          </span>
        }
      />
      <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 sm:p-5 lg:grid-cols-5">
        <SummaryCard label="Matched" value={s.matched ?? 0} tone="green" />
        <SummaryCard label="Mismatched" value={s.mismatch ?? 0} tone="red" />
        <SummaryCard label="Missing in left" value={s.missing_in_left ?? 0} tone="amber" />
        <SummaryCard label="Missing in right" value={s.missing_in_right ?? 0} tone="amber" />
        <SummaryCard label="Mismatched fields" value={totalFieldDiffs} tone="navy" />
      </div>
      {fields.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 px-4 pb-4 text-xs sm:px-5">
          <span className="font-semibold text-muted">Differences by field:</span>
          {fields.map(([f, c]) => (
            <Badge key={f} tone="red">
              {fieldLabel(f)} × {c}
            </Badge>
          ))}
        </div>
      )}
      <Tabs
        label="Filter items by status"
        idBase="recon"
        active={filter}
        onChange={setFilter}
        tabs={[
          { id: "all", label: "All", count: rec.items.length },
          ...(["mismatch", "missing_in_left", "missing_in_right", "matched"] as const).map((st) => ({
            id: st,
            label: RECON_STATUS_LABELS[st],
            count: count(st),
          })),
        ]}
      />
      <div role="tabpanel" id={`recon-panel-${filter}`} aria-labelledby={`recon-tab-${filter}`}>
        {items.length === 0 ? (
          <EmptyState title="Nothing in this category" className="py-8" />
        ) : (
          <TableWrap label="Reconciliation items">
            <table className="table-base min-w-[860px]">
              <thead>
                <tr>
                  <th scope="col">Status</th>
                  <th scope="col">Invoice key</th>
                  <th scope="col">Left</th>
                  <th scope="col">Right</th>
                  <th scope="col">Differences (left ≠ right)</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.id} className={it.status === "mismatch" ? "bg-red-50/30" : undefined}>
                    <td>
                      <ReconStatusBadge status={it.status} />
                    </td>
                    <td className="font-mono text-xs break-all">{it.match_key || "—"}</td>
                    <td className="max-w-[14rem]">
                      <InvoiceCell inv={it.left} fallbackId={it.left_invoice_id} />
                    </td>
                    <td className="max-w-[14rem]">
                      <InvoiceCell inv={it.right} fallbackId={it.right_invoice_id} />
                    </td>
                    <td className="min-w-[16rem]">
                      <Differences item={it} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )}
      </div>
    </Card>
  );
}

export function ReconcileView() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const toast = useToast();
  const selectedId = search.get("id");

  const docs = useApi<DocumentList>(`/api/documents${qs({ status: "completed,needs_review", page_size: 200 })}`);
  const history = useApi<Reconciliation[]>("/api/reconciliations?limit=20");
  const result = useApi<Reconciliation>(isUuid(selectedId) ? `/api/reconciliations/${selectedId}` : null);

  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [tolerance, setTolerance] = useState("0.01");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const documents = docs.data?.items ?? [];
  const tol = Number(tolerance);
  const tolInvalid = tolerance.trim() === "" || !Number.isFinite(tol) || tol < 0 || tol > 1000;
  const same = !!left && left === right;
  const canRun = !!left && !!right && !same && !tolInvalid && !running;

  async function run(e: FormEvent) {
    e.preventDefault();
    if (!canRun) return;
    setRunning(true);
    setRunError(null);
    try {
      const rec = await api<Reconciliation>("/api/reconciliations", {
        method: "POST",
        body: { left_document_id: left, right_document_id: right, amount_tolerance: tol },
      });
      result.mutate(rec);
      history.reload();
      router.replace(`${pathname}?id=${rec.id}`, { scroll: false });
      toast.success("Cross-verification complete", `${rec.summary.matched ?? 0} matched, ${rec.summary.mismatch ?? 0} mismatched`);
    } catch (err) {
      setRunError(errorMessage(err));
    } finally {
      setRunning(false);
    }
  }

  const docLabel = (d: (typeof documents)[number]) =>
    `${d.original_filename} — ${fileTypeLabel(d.file_type)} · ${d.invoice_count} invoice${d.invoice_count === 1 ? "" : "s"}`;

  return (
    <>
      <PageHeader
        title="Cross-verify documents"
        description="Compare two processed documents invoice by invoice, e.g. a supplier's PDF statement against your ERP's Excel export."
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-6 xl:col-span-2">
          <Card aria-labelledby="recon-setup">
            <CardHeader
              id="recon-setup"
              title="Choose documents"
              description="Invoices are matched by invoice number, then by supplier + date + total; matched pairs are compared field by field."
            />
            {docs.error && !docs.data ? (
              <ErrorState title="Could not load documents" error={docs.error} onRetry={docs.reload} />
            ) : !docs.data ? (
              <LoadingState label="Loading processed documents…" />
            ) : documents.length < 2 ? (
              <EmptyState
                icon={<GitCompareArrows className="size-5" aria-hidden />}
                title="At least two processed documents are needed"
                description="Upload and process documents on the dashboard first (status Completed or Needs review)."
              />
            ) : (
              <form onSubmit={run} className="p-4 sm:p-5">
                <div className="grid grid-cols-1 items-end gap-3 md:grid-cols-[1fr_auto_1fr]">
                  <div className="min-w-0">
                    <label htmlFor="recon-left" className="form-label">
                      Left document
                    </label>
                    <select id="recon-left" className="form-control" value={left} onChange={(e) => setLeft(e.target.value)} required>
                      <option value="">Select a document…</option>
                      {documents.map((d) => (
                        <option key={d.id} value={d.id}>
                          {docLabel(d)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button
                    variant="ghost"
                    className="justify-self-center"
                    onClick={() => {
                      setLeft(right);
                      setRight(left);
                    }}
                    aria-label="Swap left and right documents"
                    icon={<ArrowLeftRight className="size-4" aria-hidden />}
                  />
                  <div className="min-w-0">
                    <label htmlFor="recon-right" className="form-label">
                      Right document
                    </label>
                    <select id="recon-right" className="form-control" value={right} onChange={(e) => setRight(e.target.value)} required>
                      <option value="">Select a document…</option>
                      {documents.map((d) => (
                        <option key={d.id} value={d.id}>
                          {docLabel(d)}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap items-end gap-3">
                  <div>
                    <label htmlFor="recon-tol" className="form-label">
                      Amount tolerance
                    </label>
                    <input
                      id="recon-tol"
                      type="number"
                      min={0}
                      max={1000}
                      step="0.01"
                      inputMode="decimal"
                      className="form-control w-36"
                      value={tolerance}
                      onChange={(e) => setTolerance(e.target.value)}
                      aria-invalid={tolInvalid || undefined}
                      aria-describedby="recon-tol-hint"
                    />
                  </div>
                  <Button type="submit" variant="primary" loading={running} disabled={!canRun} icon={<Play className="size-4" aria-hidden />}>
                    Run cross-verification
                  </Button>
                  <p id="recon-tol-hint" className="w-full text-xs text-muted">
                    Amounts within ± tolerance count as equal (0 – 1000). Supplier names are compared fuzzily.
                  </p>
                </div>
                {same && <p className="mt-2 text-sm text-red-800">Choose two different documents.</p>}
                {runError && (
                  <Alert className="mt-3" title="Cross-verification failed">
                    {runError}
                  </Alert>
                )}
              </form>
            )}
          </Card>
        </div>

        <Card aria-labelledby="recon-history" className="h-fit">
          <CardHeader id="recon-history" title="Previous runs" description="Click one to open its result" />
          {history.error && !history.data ? (
            <ErrorState title="Could not load history" error={history.error} onRetry={history.reload} />
          ) : !history.data ? (
            <LoadingState label="Loading history…" />
          ) : history.data.length === 0 ? (
            <EmptyState icon={<Clock className="size-5" aria-hidden />} title="No cross-verifications yet" className="py-8" />
          ) : (
            <ul className="max-h-[26rem] divide-y divide-line overflow-y-auto">
              {history.data.map((r) => {
                const current = r.id === selectedId;
                return (
                  <li key={r.id}>
                    <button
                      type="button"
                      onClick={() => router.replace(`${pathname}?id=${r.id}`, { scroll: false })}
                      aria-current={current ? "true" : undefined}
                      className={cn(
                        "w-full px-4 py-3 text-left text-sm transition-colors hover:bg-primary-50/60",
                        current && "bg-accent-soft/60",
                      )}
                    >
                      <span className="flex items-center gap-1.5 font-medium text-primary-dark">
                        <GitCompareArrows className="size-3.5 shrink-0 opacity-60" aria-hidden />
                        <span className="truncate">{r.left_document_name ?? "?"}</span>
                      </span>
                      <span className="flex items-center gap-1.5 text-muted">
                        <ArrowLeftRight className="size-3.5 shrink-0" aria-label="versus" />
                        <span className="truncate">{r.right_document_name ?? "?"}</span>
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
                        <Badge tone="green">{r.summary.matched ?? 0} matched</Badge>
                        {(r.summary.mismatch ?? 0) > 0 && <Badge tone="red">{r.summary.mismatch} mismatch</Badge>}
                        {(r.summary.missing_in_left ?? 0) + (r.summary.missing_in_right ?? 0) > 0 && (
                          <Badge tone="amber">{(r.summary.missing_in_left ?? 0) + (r.summary.missing_in_right ?? 0)} missing</Badge>
                        )}
                        <span className="text-muted">{formatDateTime(r.created_at)}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </div>

      <div className="mt-6">
        {result.error ? (
          <Card>
            <ErrorState title="Could not load this cross-verification" error={result.error} onRetry={result.reload} />
          </Card>
        ) : selectedId && !result.data ? (
          <Card>
            <LoadingState label="Loading result…" />
          </Card>
        ) : result.data ? (
          <ResultView key={result.data.id} rec={result.data} />
        ) : null}
      </div>
    </>
  );
}
