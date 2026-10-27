"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Receipt, X } from "lucide-react";
import { qs } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { formatNumber, shortId } from "@/lib/format";
import type { InvoiceList } from "@/lib/types";
import { InvoicesTable, type SortKey } from "@/components/invoices-table";
import { Pagination } from "@/components/controls";
import { Card, CardHeader, EmptyState, ErrorState, LoadingState, PageHeader, Spinner } from "@/components/ui";
import { INVOICE_FILTER_KEYS, InvoiceFilters, type InvoiceFilterValues } from "./invoice-filters";

const PAGE_SIZE = 25;
const SORTS: { value: SortKey; label: string }[] = [
  { value: "created_desc", label: "Newest extracted" },
  { value: "date_desc", label: "Invoice date (newest)" },
  { value: "date_asc", label: "Invoice date (oldest)" },
  { value: "total_desc", label: "Total (highest)" },
  { value: "total_asc", label: "Total (lowest)" },
  { value: "issues_desc", label: "Most issues" },
];

export function InvoiceListView() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();

  const filters: InvoiceFilterValues = {};
  for (const k of INVOICE_FILTER_KEYS) {
    const v = search.get(k);
    if (v) filters[k] = v;
  }
  const documentId = search.get("document_id");
  const sortParam = search.get("sort") as SortKey | null;
  const sort: SortKey = sortParam && SORTS.some((s) => s.value === sortParam) ? sortParam : "created_desc";
  const page = Math.max(1, Number(search.get("page")) || 1);

  const { data, error, loading, reload } = useApi<InvoiceList>(
    `/api/invoices${qs({ ...filters, document_id: documentId, sort, page, page_size: PAGE_SIZE })}`,
  );

  function navigate(next: Record<string, string | number | null | undefined>) {
    router.push(`${pathname}${qs(next)}`, { scroll: false });
  }
  const base = { ...filters, document_id: documentId, sort: sort === "created_desc" ? null : sort };

  return (
    <>
      <PageHeader
        title="Invoices"
        description="Every invoice extracted from your documents. Filter, sort and open one to review or correct it."
      />

      <Card className="mb-6">
        <InvoiceFilters key={search.toString()} values={filters} onApply={(v) => navigate({ ...v, document_id: documentId, sort: base.sort })} />
        {documentId && (
          <div className="border-t border-line px-4 py-2.5 sm:px-5">
            <span className="inline-flex items-center gap-2 rounded-full bg-primary-50 px-3 py-1 text-xs font-medium text-primary-dark ring-1 ring-primary-200">
              From document{" "}
              <Link href={`/documents/${documentId}`} className="font-mono underline">
                {shortId(documentId)}
              </Link>
              <button
                type="button"
                className="rounded-full p-0.5 hover:bg-primary-100"
                onClick={() => navigate({ ...base, document_id: null })}
                aria-label="Remove document filter"
              >
                <X className="size-3" aria-hidden />
              </button>
            </span>
          </div>
        )}
      </Card>

      <Card aria-labelledby="inv-results">
        <CardHeader
          id="inv-results"
          title={data ? `${formatNumber(data.meta.total)} ${data.meta.total === 1 ? "invoice" : "invoices"}` : "Invoices"}
          description={loading && data ? <Spinner label="Updating…" /> : undefined}
          actions={
            <>
              <label htmlFor="inv-sort" className="text-xs font-semibold text-muted">
                Sort by
              </label>
              <select
                id="inv-sort"
                className="form-control h-8 w-auto py-1 text-xs"
                value={sort}
                onChange={(e) => navigate({ ...base, sort: e.target.value === "created_desc" ? null : e.target.value })}
              >
                {SORTS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </>
          }
        />
        {error && !loading ? (
          <ErrorState title="Could not load invoices" error={error} onRetry={reload} />
        ) : !data ? (
          <LoadingState label="Loading invoices…" />
        ) : data.items.length === 0 ? (
          <EmptyState
            icon={<Receipt className="size-5" aria-hidden />}
            title="No invoices match"
            description={
              Object.keys(filters).length || documentId
                ? "Try removing a filter or widening the date / amount range."
                : "Upload documents on the dashboard; extracted invoices will show up here."
            }
          />
        ) : (
          <div className={loading ? "opacity-60 transition-opacity" : undefined}>
            <InvoicesTable
              invoices={data.items}
              sort={sort}
              onSort={(s) => navigate({ ...base, sort: s === "created_desc" ? null : s })}
            />
            <Pagination
              page={data.meta.page}
              pageSize={data.meta.page_size}
              total={data.meta.total}
              onPage={(p) => navigate({ ...base, page: p > 1 ? p : null })}
              label="invoices"
            />
          </div>
        )}
      </Card>
    </>
  );
}
