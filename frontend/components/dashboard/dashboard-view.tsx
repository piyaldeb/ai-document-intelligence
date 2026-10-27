"use client";

import { useState } from "react";
import { FileStack, RefreshCw, RotateCcw } from "lucide-react";
import { api, errorMessage, qs } from "@/lib/api";
import { useApi, useNow, usePolling } from "@/lib/hooks";
import { pluralize } from "@/lib/format";
import { DOCUMENT_STATUSES, DOCUMENT_STATUS_LABELS, isActive } from "@/lib/labels";
import type { DocumentList, DocumentSummary, ReprocessResponse, Stats } from "@/lib/types";
import { DocumentsTable } from "@/components/documents-table";
import { Pagination } from "@/components/controls";
import { useToast } from "@/components/toast";
import { Button, Card, CardHeader, EmptyState, ErrorState, LoadingState, PageHeader, Spinner } from "@/components/ui";
import { CurrencyTotals, StatCards, TopIssues } from "./stats-panel";
import { UploadZone } from "./upload-zone";

const PAGE_SIZE = 15;
const POLL_MS = 2000;

export function DashboardView() {
  const toast = useToast();
  const now = useNow();
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  const stats = useApi<Stats>("/api/stats");
  const docs = useApi<DocumentList>(`/api/documents${qs({ status, page, page_size: PAGE_SIZE })}`);
  const items = docs.data?.items ?? [];
  const activeIds = items.filter((d) => isActive(d.status)).map((d) => d.id);

  // Live progress: poll only the visible documents that are still queued/processing.
  usePolling(
    async () => {
      if (!activeIds.length) return;
      const res = await api<DocumentList>(`/api/documents${qs({ ids: activeIds.join(","), page_size: 200 })}`);
      const fresh = new Map(res.items.map((d) => [d.id, d]));
      const settled = items.some((d) => {
        const u = fresh.get(d.id);
        return !!u && isActive(d.status) && !isActive(u.status);
      });
      docs.mutate((prev) => prev && { ...prev, items: prev.items.map((d) => fresh.get(d.id) ?? d) });
      if (settled) stats.reload();
    },
    activeIds.length ? POLL_MS : null,
  );

  function onUploaded() {
    setStatus("");
    setPage(1);
    docs.reload();
    stats.reload();
  }

  async function reprocess(doc: DocumentSummary) {
    setBusyId(doc.id);
    try {
      await api<ReprocessResponse>(`/api/documents/${doc.id}/reprocess`, { method: "POST" });
      docs.mutate(
        (prev) =>
          prev && {
            ...prev,
            items: prev.items.map((d) =>
              d.id === doc.id ? { ...d, status: "queued", stage: "queued", progress: 0, error_code: null, error_message: null } : d,
            ),
          },
      );
      toast.success("Queued for reprocessing", doc.original_filename);
      stats.reload();
    } catch (err) {
      toast.error("Could not reprocess", errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  async function remove(doc: DocumentSummary) {
    try {
      await api<void>(`/api/documents/${doc.id}`, { method: "DELETE" });
      toast.success("Document deleted", doc.original_filename);
      if (items.length === 1 && page > 1) setPage(page - 1);
      docs.reload();
      stats.reload();
    } catch (err) {
      toast.error("Could not delete", errorMessage(err));
    }
  }

  async function retryFailed() {
    setRetrying(true);
    try {
      const res = await api<ReprocessResponse>("/api/jobs/retry-failed", { method: "POST" });
      if (res.queued.length) toast.success(`${pluralize(res.queued.length, "failed document")} re-queued`);
      else toast.info("There are no failed documents to retry");
      docs.reload();
      stats.reload();
    } catch (err) {
      toast.error("Could not retry failed documents", errorMessage(err));
    } finally {
      setRetrying(false);
    }
  }

  const failedCount = stats.data?.documents.failed ?? 0;
  const total = docs.data?.meta.total ?? 0;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Upload documents, follow processing in real time and jump into anything that needs a human."
      />

      <StatCards stats={stats.data} error={stats.error} onRetry={stats.reload} />

      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <UploadZone onUploaded={onUploaded} />
        </div>
        <div className="flex flex-col gap-6">
          <CurrencyTotals stats={stats.data} />
          <TopIssues stats={stats.data} />
        </div>
      </div>

      <Card aria-labelledby="docs-title">
        <CardHeader
          id="docs-title"
          title="Recent documents"
          description={
            activeIds.length ? (
              <Spinner label={`${pluralize(activeIds.length, "document")} in progress · updating live`} />
            ) : (
              "Newest first"
            )
          }
          actions={
            <>
              <label className="sr-only" htmlFor="doc-status">
                Filter by status
              </label>
              <select
                id="doc-status"
                className="form-control h-8 w-auto py-1 text-xs"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">All statuses</option>
                <option value="queued,processing">In progress</option>
                {DOCUMENT_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {DOCUMENT_STATUS_LABELS[s]}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                variant="secondary"
                onClick={retryFailed}
                loading={retrying}
                disabled={!failedCount}
                title={failedCount ? undefined : "No failed documents"}
                icon={<RotateCcw className="size-3.5" aria-hidden />}
              >
                Retry all failed{failedCount ? ` (${failedCount})` : ""}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  docs.reload();
                  stats.reload();
                }}
                aria-label="Refresh documents"
                icon={<RefreshCw className={docs.loading ? "size-3.5 animate-spin" : "size-3.5"} aria-hidden />}
              >
                <span className="hidden sm:inline">Refresh</span>
              </Button>
            </>
          }
        />
        {docs.error && !docs.data ? (
          <ErrorState title="Could not load documents" error={docs.error} onRetry={docs.reload} />
        ) : !docs.data ? (
          <LoadingState label="Loading documents…" />
        ) : items.length === 0 ? (
          <EmptyState
            icon={<FileStack className="size-5" aria-hidden />}
            title={status ? "No documents with this status" : "No documents yet"}
            description={status ? "Try another status filter." : "Upload your first invoices above to get started."}
          />
        ) : (
          <>
            {docs.error && (
              <p className="border-b border-red-200 bg-red-50 px-5 py-2 text-xs text-red-800" role="alert">
                Refresh failed: {docs.error.message}
              </p>
            )}
            <DocumentsTable documents={items} now={now} busyId={busyId} onReprocess={reprocess} onDelete={remove} />
            <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} label="documents" />
          </>
        )}
      </Card>
    </>
  );
}
