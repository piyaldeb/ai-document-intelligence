"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight, CircleAlert, ClipboardCheck, ExternalLink, RefreshCw, TriangleAlert } from "lucide-react";
import { api, isAbortError, qs } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { formatDate, formatMoney, formatNumber } from "@/lib/format";
import { ISSUE_CODES, fieldLabel } from "@/lib/labels";
import type { InvoiceDetail, InvoiceList, IssueOut } from "@/lib/types";
import { IssueCounts } from "@/components/badges";
import { Pagination } from "@/components/controls";
import { sourceLabel } from "@/components/invoices-table";
import { Button, ButtonLink, Card, EmptyState, ErrorState, LoadingState, PageHeader, Spinner } from "@/components/ui";

const PAGE_SIZE = 20;
const CONCURRENCY = 4;
const SEVERITY_ORDER: Record<string, number> = { error: 0, warning: 1, info: 2 };

type IssueMap = Record<string, IssueOut[] | "error">;

/**
 * The list endpoint returns counts only, so issue messages for the visible rows are loaded
 * from GET /api/invoices/{id} with a small concurrency limit.
 */
function useIssuesFor(ids: string[]): IssueMap {
  const [map, setMap] = useState<IssueMap>({});
  const key = ids.join(",");
  useEffect(() => {
    if (!key) return;
    const queue = key.split(",");
    const ctrl = new AbortController();
    async function worker() {
      while (queue.length && !ctrl.signal.aborted) {
        const id = queue.shift()!;
        try {
          const inv = await api<InvoiceDetail>(`/api/invoices/${id}`, { signal: ctrl.signal });
          setMap((m) => ({ ...m, [id]: inv.issues }));
        } catch (err) {
          if (isAbortError(err) || ctrl.signal.aborted) return;
          setMap((m) => ({ ...m, [id]: "error" }));
        }
      }
    }
    for (let i = 0; i < CONCURRENCY; i++) void worker();
    return () => ctrl.abort();
  }, [key]);
  return map;
}

function TopIssues({ issues }: { issues: IssueOut[] | "error" | undefined }) {
  if (issues === undefined) return <Spinner label="Loading issues…" />;
  if (issues === "error") return <p className="text-xs text-muted">Issue details unavailable.</p>;
  const top = issues
    .filter((i) => i.severity !== "info")
    .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3))
    .slice(0, 3);
  const more = issues.filter((i) => i.severity !== "info").length - top.length;
  if (!top.length) return <p className="text-xs text-muted">No open errors or warnings.</p>;
  return (
    <ul className="space-y-1">
      {top.map((i) => (
        <li key={i.id} className="flex items-start gap-1.5 text-sm">
          {i.severity === "error" ? (
            <CircleAlert className="mt-0.5 size-3.5 shrink-0 text-red-700" aria-label="Error" />
          ) : (
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-amber-700" aria-label="Warning" />
          )}
          <span className="min-w-0 break-words">
            {i.message}
            {i.field && <span className="ml-1 text-xs text-muted">({fieldLabel(i.field)})</span>}
          </span>
        </li>
      ))}
      {more > 0 && <li className="pl-5 text-xs text-muted">+ {more} more</li>}
    </ul>
  );
}

export function ReviewQueue() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const issueCode = search.get("issue_code") ?? "";
  const page = Math.max(1, Number(search.get("page")) || 1);

  const { data, error, loading, reload } = useApi<InvoiceList>(
    `/api/invoices${qs({ review_status: "needs_review", sort: "issues_desc", issue_code: issueCode, page, page_size: PAGE_SIZE })}`,
  );
  const issues = useIssuesFor(data?.items.map((i) => i.id) ?? []);

  function go(next: { issue_code?: string; page?: number }) {
    router.push(`${pathname}${qs({ issue_code: next.issue_code ?? issueCode, page: next.page && next.page > 1 ? next.page : null })}`, {
      scroll: false,
    });
  }

  return (
    <>
      <PageHeader
        title="Review queue"
        description="Invoices flagged by validation, worst first. Fix the values or approve them to clear the queue."
        actions={
          <>
            <label htmlFor="queue-issue" className="sr-only">
              Filter by issue
            </label>
            <select
              id="queue-issue"
              className="form-control h-10 w-auto"
              value={issueCode}
              onChange={(e) => go({ issue_code: e.target.value, page: 1 })}
            >
              <option value="">All issues</option>
              {Object.entries(ISSUE_CODES).map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
            <Button onClick={reload} icon={<RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} aria-hidden />}>
              Refresh
            </Button>
          </>
        }
      />

      {error ? (
        <Card>
          <ErrorState title="Could not load the review queue" error={error} onRetry={reload} />
        </Card>
      ) : !data ? (
        <Card>
          <LoadingState label="Loading review queue…" />
        </Card>
      ) : data.items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<ClipboardCheck className="size-5" aria-hidden />}
            title={issueCode ? "No invoices with this issue need review" : "The review queue is empty"}
            description={issueCode ? "Choose another issue or clear the filter." : "Every extracted invoice passed validation or has been approved."}
            action={
              <ButtonLink href="/invoices" variant="secondary">
                Browse all invoices
              </ButtonLink>
            }
          />
        </Card>
      ) : (
        <>
          <p className="mb-3 text-sm text-muted" aria-live="polite">
            <span className="font-semibold text-ink">{formatNumber(data.meta.total)}</span>{" "}
            {data.meta.total === 1 ? "invoice needs" : "invoices need"} review
            {loading && <span className="ml-2"><Spinner /></span>}
          </p>
          <ol className="space-y-3">
            {data.items.map((inv) => (
              <li key={inv.id}>
                <Card className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between sm:p-5">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <h2 className="text-base font-semibold break-all">
                        <Link href={`/invoices/${inv.id}`} className="hover:underline">
                          {inv.invoice_number || <span className="text-muted italic">No invoice number</span>}
                        </Link>
                      </h2>
                      <IssueCounts errors={inv.error_count} warnings={inv.warning_count} />
                    </div>
                    <p className="mt-1 text-sm text-muted">
                      {inv.supplier_name || "Unknown supplier"} · {formatDate(inv.invoice_date)} ·{" "}
                      <span className="font-semibold text-ink">{formatMoney(inv.total, inv.currency)}</span> · {sourceLabel(inv)}
                    </p>
                    <div className="mt-3">
                      <TopIssues issues={issues[inv.id]} />
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-row gap-2 sm:flex-col sm:items-stretch">
                    <ButtonLink href={`/invoices/${inv.id}`} variant="primary" size="sm">
                      Review &amp; fix
                      <ArrowRight className="size-3.5" aria-hidden />
                    </ButtonLink>
                    <ButtonLink
                      href={`/documents/${inv.document_id}?tab=text${inv.page_start ? `&page=${inv.page_start}` : ""}`}
                      variant="ghost"
                      size="sm"
                      icon={<ExternalLink className="size-3.5" aria-hidden />}
                    >
                      Source
                    </ButtonLink>
                  </div>
                </Card>
              </li>
            ))}
          </ol>
          <Card className="mt-3">
            <Pagination page={data.meta.page} pageSize={data.meta.page_size} total={data.meta.total} onPage={(p) => go({ page: p })} label="invoices" />
          </Card>
        </>
      )}
    </>
  );
}
