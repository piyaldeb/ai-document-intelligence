"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Copy, Download, Receipt, RotateCcw, Trash, TriangleAlert } from "lucide-react";
import { ApiError, api, errorMessage } from "@/lib/api";
import { useApi, usePolling } from "@/lib/hooks";
import { formatBytes, formatDateTime, formatDuration, formatNumber, pluralize } from "@/lib/format";
import { fieldLabel, fileTypeLabel, isActive, issueLabel, providerLabel, stageLabel } from "@/lib/labels";
import type { DocumentDetail, DocumentStatusOut, ReprocessResponse } from "@/lib/types";
import { DocumentStatusBadge, FileTypeIcon, SeverityBadge } from "@/components/badges";
import { ConfirmButton, TabPanel, Tabs } from "@/components/controls";
import { InvoicesTable } from "@/components/invoices-table";
import { useToast } from "@/components/toast";
import {
  Alert,
  Badge,
  Button,
  ButtonLink,
  Card,
  EmptyState,
  ErrorState,
  KeyValue,
  LoadingState,
  ProgressBar,
  buttonClass,
} from "@/components/ui";
import { FileTab } from "./file-tab";
import { HistoryTab } from "./history-tab";
import { TextTab } from "./text-tab";

const TAB_IDS = ["invoices", "text", "history", "file"] as const;
type TabId = (typeof TAB_IDS)[number];

export function DocumentView({ id }: { id: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const toast = useToast();
  const { data: doc, error, reload, mutate } = useApi<DocumentDetail>(`/api/documents/${id}`);
  const [reprocessing, setReprocessing] = useState(false);

  const active = !!doc && isActive(doc.status);

  // While queued/processing, poll the cheap status endpoint; reload the full detail when the
  // stage changes (new history events) or processing finishes.
  usePolling(
    async () => {
      const s = await api<DocumentStatusOut>(`/api/documents/${id}/status`);
      const changed = s.stage !== doc?.stage || s.status !== doc?.status;
      mutate((prev) => prev && { ...prev, ...s });
      if (changed) reload();
    },
    active ? 2000 : null,
  );

  const requestedTab = search.get("tab") as TabId | null;
  const tab: TabId =
    requestedTab && TAB_IDS.includes(requestedTab)
      ? requestedTab
      : doc?.status === "failed"
        ? "history"
        : doc && doc.invoice_count === 0 && doc.pages.length > 0
          ? "text"
          : "invoices";
  const pageParam = Number(search.get("page")) || null;

  function setQuery(next: Record<string, string | null>) {
    const sp = new URLSearchParams(search.toString());
    for (const [k, v] of Object.entries(next)) {
      if (v === null) sp.delete(k);
      else sp.set(k, v);
    }
    const q = sp.toString();
    router.replace(q ? `${pathname}?${q}` : pathname, { scroll: false });
  }

  async function reprocess() {
    setReprocessing(true);
    try {
      await api<ReprocessResponse>(`/api/documents/${id}/reprocess`, { method: "POST" });
      mutate((prev) => prev && { ...prev, status: "queued", stage: "queued", progress: 0, error_code: null, error_message: null });
      toast.success("Queued for reprocessing");
      reload();
    } catch (err) {
      toast.error("Could not reprocess", errorMessage(err));
    } finally {
      setReprocessing(false);
    }
  }

  async function remove() {
    try {
      await api<void>(`/api/documents/${id}`, { method: "DELETE" });
      toast.success("Document deleted", doc?.original_filename);
      router.push("/");
    } catch (err) {
      toast.error("Could not delete", errorMessage(err));
    }
  }

  if (error && !doc) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <Card>
        {notFound ? (
          <EmptyState
            title="Document not found"
            description="It may have been deleted."
            action={
              <ButtonLink href="/" variant="navy">
                Back to dashboard
              </ButtonLink>
            }
          />
        ) : (
          <ErrorState title="Could not load the document" error={error} onRetry={reload} />
        )}
      </Card>
    );
  }
  if (!doc) return <LoadingState label="Loading document…" />;

  const pct = doc.status === "queued" ? 0 : doc.progress;
  const meta = doc.meta ?? {};
  const sheets = Array.isArray(meta.sheets) ? (meta.sheets as unknown[]).map(String) : null;

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-3">
        <Link href="/" className="inline-flex items-center gap-1 text-sm text-muted hover:text-primary">
          <ArrowLeft className="size-4" aria-hidden />
          Dashboard
        </Link>
      </nav>

      <Card className="mb-6">
        <div className="flex flex-col gap-4 p-4 sm:p-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-start gap-2">
              <FileTypeIcon type={doc.file_type} className="mt-1.5 size-5" />
              <h1 className="text-xl font-semibold break-all sm:text-2xl">{doc.original_filename}</h1>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">
              <DocumentStatusBadge status={doc.status} />
              <Badge tone="grey">{fileTypeLabel(doc.file_type)}</Badge>
              <span>{formatBytes(doc.size_bytes)}</span>
              {doc.page_count !== null && <span>· {pluralize(doc.page_count, sheets ? "sheet" : "page")}</span>}
              <span>· {pluralize(doc.invoice_count, "invoice")}</span>
              {doc.attempts > 1 && <span>· {doc.attempts} attempts</span>}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant={doc.status === "failed" ? "primary" : "secondary"}
              size="sm"
              onClick={reprocess}
              loading={reprocessing}
              disabled={active && doc.stage !== "queued"}
              title={active ? "Already processing" : "Run the full pipeline again"}
              icon={<RotateCcw className="size-3.5" aria-hidden />}
            >
              Reprocess
            </Button>
            <a href={`/api/documents/${doc.id}/file`} download={doc.original_filename} className={buttonClass("secondary", "sm")}>
              <Download className="size-3.5" aria-hidden />
              Download
            </a>
            <ConfirmButton
              label="Delete"
              icon={<Trash className="size-3.5" aria-hidden />}
              question="Delete this document and its invoices?"
              confirmLabel="Delete"
              disabled={doc.status === "processing"}
              disabledReason="Cannot delete while processing"
              onConfirm={remove}
            />
          </div>
        </div>

        {active && (
          <div className="border-t border-line px-4 py-3 sm:px-5" aria-live="polite">
            <div className="mb-1.5 flex items-center justify-between text-sm">
              <span className="font-medium text-blue-900">{stageLabel(doc.stage)}…</span>
              <span className="font-semibold text-blue-900 tabular-nums">{pct}%</span>
            </div>
            <ProgressBar value={pct} label="Processing progress" className="h-2" />
          </div>
        )}

        {doc.status === "failed" && (
          <div className="border-t border-line px-4 py-3 sm:px-5">
            <Alert
              title={
                <>
                  Processing failed{doc.error_code && <span className="ml-1 font-mono text-xs">({doc.error_code})</span>}
                </>
              }
              actions={
                <Button size="sm" variant="primary" onClick={reprocess} loading={reprocessing} icon={<RotateCcw className="size-3.5" aria-hidden />}>
                  Reprocess
                </Button>
              }
            >
              <span className="whitespace-pre-wrap">{doc.error_message || "No error message was recorded."}</span>
            </Alert>
          </div>
        )}

        {doc.duplicate_of_id && (
          <div className="border-t border-line px-4 py-3 sm:px-5">
            <Alert tone="amber" title="Duplicate file">
              <span className="inline-flex flex-wrap items-center gap-1">
                <Copy className="size-3.5" aria-hidden />
                An identical file (same SHA-256) was uploaded earlier:{" "}
                <Link href={`/documents/${doc.duplicate_of_id}`} className="link">
                  open the original upload
                </Link>
              </span>
            </Alert>
          </div>
        )}

        <dl className="grid grid-cols-2 gap-4 border-t border-line px-4 py-4 sm:grid-cols-3 sm:px-5 lg:grid-cols-6">
          <KeyValue label="Uploaded">{formatDateTime(doc.created_at)}</KeyValue>
          <KeyValue label="Started">{formatDateTime(doc.processing_started_at)}</KeyValue>
          <KeyValue label="Finished">{formatDateTime(doc.processing_finished_at)}</KeyValue>
          <KeyValue label="Processing time">{formatDuration(doc.processing_ms)}</KeyValue>
          <KeyValue label="Extraction">{providerLabel(doc.extraction_provider)}</KeyValue>
          <KeyValue label="SHA-256">
            <span className="font-mono text-xs" title={doc.sha256}>
              {doc.sha256.slice(0, 12)}…
            </span>
          </KeyValue>
          {sheets && sheets.length > 0 && (
            <div className="col-span-2 sm:col-span-3 lg:col-span-6">
              <KeyValue label="Sheets">{sheets.join(", ")}</KeyValue>
            </div>
          )}
        </dl>
      </Card>

      {doc.issues.length > 0 && (
        <Card className="mb-6" aria-labelledby="doc-issues">
          <div className="border-b border-line px-4 py-3 sm:px-5">
            <h2 id="doc-issues" className="flex items-center gap-2 text-base font-semibold">
              <TriangleAlert className="size-4 text-accent-strong" aria-hidden />
              Document-level issues
            </h2>
          </div>
          <ul className="divide-y divide-line">
            {doc.issues.map((i) => (
              <li key={i.id} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-start sm:gap-3 sm:px-5">
                <SeverityBadge severity={i.severity} />
                <div className="min-w-0 text-sm">
                  <p className="text-ink">{i.message}</p>
                  <p className="mt-0.5 text-xs text-muted">
                    {issueLabel(i.code)} <span className="font-mono">({i.code})</span>
                    {i.field && <> · {fieldLabel(i.field)}</>}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <Tabs
          label="Document sections"
          idBase="doc"
          active={tab}
          onChange={(t) => setQuery({ tab: t, page: t === "text" ? (pageParam ? String(pageParam) : null) : null })}
          tabs={[
            { id: "invoices", label: "Invoices", count: doc.invoices.length },
            { id: "text", label: sheets ? "Extracted sheets" : "Extracted text", count: doc.pages.length },
            { id: "history", label: "Processing history", count: doc.events.length },
            { id: "file", label: "Original file" },
          ]}
        />
        <TabPanel id="invoices" active={tab} idBase="doc">
          {doc.invoices.length === 0 ? (
            <EmptyState
              icon={<Receipt className="size-5" aria-hidden />}
              title={active ? "Invoices will appear when processing finishes" : "No invoices were found"}
              description={
                active
                  ? `${stageLabel(doc.stage)} (${pct}%)`
                  : doc.status === "failed"
                    ? "Processing failed before any invoice was extracted."
                    : "The document was read but no invoice-like content was detected."
              }
            />
          ) : (
            <>
              <InvoicesTable invoices={doc.invoices} showSource showDocumentLink={false} />
              {doc.invoices.length > 1 && (
                <p className="border-t border-line px-5 py-2.5 text-xs text-muted">
                  {formatNumber(doc.invoices.filter((i) => i.review_status === "needs_review").length)} of{" "}
                  {formatNumber(doc.invoices.length)} need review ·{" "}
                  <Link href={`/invoices?document_id=${doc.id}`} className="link">
                    open in invoice list
                  </Link>
                </p>
              )}
            </>
          )}
        </TabPanel>
        <TabPanel id="text" active={tab} idBase="doc">
          <TextTab doc={doc} page={pageParam} onPage={(p) => setQuery({ tab: "text", page: String(p) })} />
        </TabPanel>
        <TabPanel id="history" active={tab} idBase="doc">
          <HistoryTab events={doc.events} active={active} />
        </TabPanel>
        <TabPanel id="file" active={tab} idBase="doc">
          <FileTab doc={doc} />
        </TabPanel>
      </Card>
    </>
  );
}
