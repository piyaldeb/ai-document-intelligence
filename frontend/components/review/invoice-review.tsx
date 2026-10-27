"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, FileText, ScanText } from "lucide-react";
import { ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { formatDate, formatDateTime, formatMoney, formatNumber } from "@/lib/format";
import type { InvoiceDetail } from "@/lib/types";
import { IssueCounts, ReviewBadge } from "@/components/badges";
import { sourceLabel } from "@/components/invoices-table";
import { ButtonLink, Card, EmptyState, ErrorState, KeyValue, LoadingState } from "@/components/ui";
import { InvoiceEditor } from "./invoice-editor";

export function InvoiceReview({ id }: { id: string }) {
  const { data: invoice, error, reload, mutate } = useApi<InvoiceDetail>(`/api/invoices/${id}`);
  // Bumped whenever the server returns a new version, so the editor re-initialises its form.
  const [version, setVersion] = useState(0);

  if (error && !invoice) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <Card>
        {notFound ? (
          <EmptyState
            title="Invoice not found"
            description="It may have been removed when its document was deleted or reprocessed."
            action={
              <ButtonLink href="/invoices" variant="navy">
                Back to invoices
              </ButtonLink>
            }
          />
        ) : (
          <ErrorState title="Could not load the invoice" error={error} onRetry={reload} />
        )}
      </Card>
    );
  }
  if (!invoice) return <LoadingState label="Loading invoice…" />;

  const page = invoice.page_start;
  const docTextHref = `/documents/${invoice.document_id}?tab=text${page ? `&page=${page}` : ""}`;
  const minOcr = invoice.raw_extraction?.min_ocr_confidence;

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <Link href="/invoices" className="inline-flex items-center gap-1 text-muted hover:text-primary">
          <ArrowLeft className="size-4" aria-hidden />
          Invoices
        </Link>
        <Link href="/review" className="text-muted hover:text-primary">
          Review queue
        </Link>
      </nav>

      <Card className="mb-6">
        <div className="flex flex-col gap-4 p-4 sm:p-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold tracking-wide text-muted uppercase">
              Invoice #{invoice.sequence} in its document
            </p>
            <h1 className="mt-0.5 text-xl font-semibold break-all sm:text-2xl">
              {invoice.invoice_number || <span className="text-muted italic">No invoice number</span>}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">
              <ReviewBadge status={invoice.review_status} />
              <IssueCounts errors={invoice.error_count} warnings={invoice.warning_count} />
              <span className="font-heading text-base font-semibold text-primary-dark">
                {formatMoney(invoice.total, invoice.currency)}
              </span>
              {invoice.supplier_name && <span>· {invoice.supplier_name}</span>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <ButtonLink href={docTextHref} size="sm" variant="secondary" icon={<ScanText className="size-3.5" aria-hidden />}>
              View source text
            </ButtonLink>
            <ButtonLink
              href={`/documents/${invoice.document_id}?tab=file`}
              size="sm"
              variant="ghost"
              icon={<FileText className="size-3.5" aria-hidden />}
            >
              Original file
            </ButtonLink>
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-4 border-t border-line px-4 py-4 sm:grid-cols-3 sm:px-5 lg:grid-cols-6">
          <KeyValue label="Document">
            <Link href={`/documents/${invoice.document_id}`} className="link break-all">
              {invoice.document_name ?? "Open document"}
            </Link>
          </KeyValue>
          <KeyValue label="Source">{sourceLabel(invoice)}</KeyValue>
          <KeyValue label="Invoice date">{formatDate(invoice.invoice_date)}</KeyValue>
          <KeyValue label="Extraction">
            {invoice.extraction_method}
            {invoice.model && <span className="block truncate font-mono text-xs text-muted">{invoice.model}</span>}
          </KeyValue>
          <KeyValue label="OCR confidence">
            {typeof minOcr === "number" ? `${formatNumber(minOcr)}/100 (lowest page)` : "n/a (no OCR needed)"}
          </KeyValue>
          <KeyValue label="Last updated">{formatDateTime(invoice.updated_at)}</KeyValue>
        </dl>
      </Card>

      <InvoiceEditor
        key={`${invoice.id}:${version}`}
        invoice={invoice}
        onUpdated={(next) => {
          mutate(next);
          setVersion((v) => v + 1);
        }}
      />

      <Card className="mt-6">
        <details className="group">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 sm:px-5 [&::-webkit-details-marker]:hidden">
            <span>
              <span className="font-heading text-base font-semibold text-primary-dark">Source text</span>
              <span className="ml-2 text-xs text-muted">
                {formatNumber(invoice.source_text.length)} characters the extractor saw
              </span>
            </span>
            <span className="text-xs font-semibold text-primary group-open:hidden">Show</span>
            <span className="hidden text-xs font-semibold text-primary group-open:inline">Hide</span>
          </summary>
          <div className="border-t border-line p-4 sm:p-5">
            {invoice.source_text.trim() ? (
              <pre
                tabIndex={0}
                className="max-h-[60vh] overflow-auto rounded-lg border border-line bg-slate-50 p-4 font-mono text-xs leading-relaxed break-words whitespace-pre-wrap text-ink"
              >
                {invoice.source_text}
              </pre>
            ) : (
              <p className="text-sm text-muted">
                No source text was stored for this invoice (e.g. it came from structured spreadsheet rows).
              </p>
            )}
            <p className="mt-2 text-xs">
              <Link href={docTextHref} className="link">
                Open the full extracted text in the document viewer
              </Link>
            </p>
          </div>
        </details>
      </Card>
    </>
  );
}
