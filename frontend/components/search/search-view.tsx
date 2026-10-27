"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { FileSearch, Funnel, Receipt, Search as SearchIcon, X } from "lucide-react";
import { ApiError, qs } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { formatDate, formatMoney, formatNumber } from "@/lib/format";
import { FILE_TYPE_LABELS } from "@/lib/labels";
import type { SearchMode, SearchResponse } from "@/lib/types";
import { MatchBadge, ReviewBadge } from "@/components/badges";
import { Segmented } from "@/components/controls";
import { Highlighted } from "@/components/highlight";
import { Alert, Badge, Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, Spinner } from "@/components/ui";

const MODES: { value: SearchMode; label: string; hint: string }[] = [
  { value: "hybrid", label: "Hybrid", hint: "Keyword + semantic, fused with reciprocal rank fusion" },
  { value: "keyword", label: "Keyword", hint: "Full-text and fuzzy matching on fields and page text" },
  { value: "semantic", label: "Semantic", hint: "Meaning-based vector similarity" },
];
const FILTER_KEYS = ["supplier", "currency", "date_from", "date_to", "min_total", "max_total", "review_status", "file_type"] as const;
type FilterKey = (typeof FILTER_KEYS)[number];
const EXAMPLES = ["consulting services", "late payment fee", "office supplies", "INV-2024"];

export function SearchView() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const q = search.get("q")?.trim() ?? "";
  const modeParam = search.get("mode") as SearchMode | null;
  const mode: SearchMode = modeParam && MODES.some((m) => m.value === modeParam) ? modeParam : "hybrid";
  const filters: Partial<Record<FilterKey, string>> = {};
  for (const k of FILTER_KEYS) {
    const v = search.get(k);
    if (v) filters[k] = v;
  }
  const activeFilters = Object.keys(filters).length;

  const [draftMode, setDraftMode] = useState<SearchMode>(mode);
  const [showFilters, setShowFilters] = useState(activeFilters > 0);
  const [lastMode, setLastMode] = useState(mode);
  if (lastMode !== mode) {
    // URL changed (back/forward or a new search): mirror it in the toggle.
    setLastMode(mode);
    setDraftMode(mode);
  }

  const { data, error, loading } = useApi<SearchResponse>(
    q ? `/api/search${qs({ q, mode, ...filters, limit: 30 })}` : null,
  );

  function run(params: { q: string; mode: SearchMode; filters: Partial<Record<FilterKey, string>> }) {
    router.push(`${pathname}${qs({ q: params.q, mode: params.mode === "hybrid" ? null : params.mode, ...params.filters })}`);
  }

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const nextQ = String(fd.get("q") ?? "").trim();
    const nextFilters: Partial<Record<FilterKey, string>> = {};
    for (const k of FILTER_KEYS) {
      const v = fd.get(k);
      if (typeof v === "string" && v.trim()) nextFilters[k] = k === "currency" ? v.trim().toUpperCase() : v.trim();
      else if (!showFilters && filters[k]) nextFilters[k] = filters[k];
    }
    if (!nextQ) return;
    run({ q: nextQ, mode: draftMode, filters: nextFilters });
  }

  const semanticDisabled = error instanceof ApiError && error.status === 400 && /semantic/i.test(error.message);

  return (
    <>
      <PageHeader
        title="Search"
        description="Find anything in previously processed documents: invoice fields, page text and meaning."
      />

      <Card className="mb-6">
        <form key={search.toString()} onSubmit={submit} role="search" aria-label="Search documents" className="p-4 sm:p-5">
          <div className="flex flex-col gap-3 md:flex-row">
            <div className="relative flex-1">
              <label htmlFor="search-q" className="sr-only">
                Search query
              </label>
              <SearchIcon className="pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2 text-slate-400" aria-hidden />
              <input
                id="search-q"
                name="q"
                type="search"
                defaultValue={q}
                required
                maxLength={500}
                placeholder="e.g. invoices from Acme for cloud hosting"
                className="form-control h-12 pl-11 text-base"
                autoFocus={!q}
              />
            </div>
            <Button type="submit" variant="primary" className="h-12 px-6" icon={<SearchIcon className="size-4" aria-hidden />}>
              Search
            </Button>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <Segmented name="mode" label="Search mode" options={MODES} value={draftMode} onChange={setDraftMode} />
            <Button
              variant="ghost"
              size="sm"
              aria-expanded={showFilters}
              aria-controls="search-filters"
              onClick={() => setShowFilters((s) => !s)}
              icon={<Funnel className="size-3.5" aria-hidden />}
            >
              Filters{activeFilters ? ` (${activeFilters})` : ""}
            </Button>
          </div>
          {showFilters && (
            <div id="search-filters" className="mt-4 grid grid-cols-1 gap-3 border-t border-line pt-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <label htmlFor="s-supplier" className="form-label">
                  Supplier
                </label>
                <input id="s-supplier" name="supplier" defaultValue={filters.supplier} className="form-control" maxLength={200} />
              </div>
              <div>
                <label htmlFor="s-currency" className="form-label">
                  Currency
                </label>
                <input
                  id="s-currency"
                  name="currency"
                  defaultValue={filters.currency}
                  className="form-control uppercase"
                  maxLength={3}
                  pattern="[A-Za-z]{3}"
                  placeholder="e.g. EUR"
                />
              </div>
              <div>
                <label htmlFor="s-from" className="form-label">
                  Date from
                </label>
                <input id="s-from" name="date_from" type="date" defaultValue={filters.date_from} className="form-control" />
              </div>
              <div>
                <label htmlFor="s-to" className="form-label">
                  Date to
                </label>
                <input id="s-to" name="date_to" type="date" defaultValue={filters.date_to} className="form-control" />
              </div>
              <div>
                <label htmlFor="s-min" className="form-label">
                  Min total
                </label>
                <input id="s-min" name="min_total" type="number" step="0.01" defaultValue={filters.min_total} className="form-control" />
              </div>
              <div>
                <label htmlFor="s-max" className="form-label">
                  Max total
                </label>
                <input id="s-max" name="max_total" type="number" step="0.01" defaultValue={filters.max_total} className="form-control" />
              </div>
              <div>
                <label htmlFor="s-review" className="form-label">
                  Review status
                </label>
                <select id="s-review" name="review_status" defaultValue={filters.review_status ?? ""} className="form-control">
                  <option value="">Any</option>
                  <option value="needs_review">Needs review</option>
                  <option value="ok">OK</option>
                  <option value="approved">Approved</option>
                </select>
              </div>
              <div>
                <label htmlFor="s-type" className="form-label">
                  File type
                </label>
                <select id="s-type" name="file_type" defaultValue={filters.file_type ?? ""} className="form-control">
                  <option value="">Any</option>
                  {Object.entries(FILE_TYPE_LABELS).map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
              </div>
              {activeFilters > 0 && (
                <div className="sm:col-span-2 lg:col-span-4">
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={<X className="size-3.5" aria-hidden />}
                    onClick={() => (q ? run({ q, mode, filters: {} }) : router.push(pathname))}
                  >
                    Clear filters
                  </Button>
                </div>
              )}
            </div>
          )}
        </form>
      </Card>

      {!q ? (
        <Card>
          <EmptyState
            icon={<FileSearch className="size-5" aria-hidden />}
            title="Search your processed documents"
            description={
              <>
                <span className="block">Hybrid mode combines exact keyword hits with semantic matches.</span>
                <span className="mt-3 flex flex-wrap justify-center gap-2">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex}
                      type="button"
                      className="rounded-full bg-primary-50 px-3 py-1 text-xs font-medium text-primary ring-1 ring-primary-200 hover:bg-primary-100"
                      onClick={() => run({ q: ex, mode: draftMode, filters })}
                    >
                      {ex}
                    </button>
                  ))}
                </span>
              </>
            }
          />
        </Card>
      ) : semanticDisabled ? (
        <Alert
          tone="amber"
          title="Semantic search is disabled on this deployment"
          actions={
            <Button size="sm" variant="primary" onClick={() => run({ q, mode: "keyword", filters })}>
              Search by keyword instead
            </Button>
          }
        >
          Embeddings are turned off on the server, so only keyword search is available.
        </Alert>
      ) : error ? (
        <Card>
          <ErrorState title="Search failed" error={error} />
        </Card>
      ) : !data ? (
        <Card>
          <LoadingState label="Searching…" />
        </Card>
      ) : (
        <section aria-labelledby="results-title">
          <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
            <h2 id="results-title" className="text-base font-semibold" aria-live="polite">
              {formatNumber(data.results.length)} {data.results.length === 1 ? "result" : "results"} for “{data.query}”
            </h2>
            <span className="text-xs text-muted">
              {data.mode} search · took {formatNumber(data.took_ms)} ms
            </span>
            {loading && <Spinner label="Updating…" />}
          </div>
          {data.results.length === 0 ? (
            <Card>
              <EmptyState
                title="No matches"
                description={
                  mode === "keyword"
                    ? "Try different words or switch to Hybrid / Semantic to match by meaning."
                    : "Try different words or remove filters."
                }
              />
            </Card>
          ) : (
            <ol className={loading ? "space-y-3 opacity-60" : "space-y-3"}>
              {data.results.map((hit, i) => {
                const docHref = `/documents/${hit.document_id}${hit.page_number ? `?tab=text&page=${hit.page_number}` : ""}`;
                const inv = hit.invoice;
                return (
                  <li key={`${hit.document_id}-${hit.invoice_id ?? ""}-${hit.page_number ?? ""}-${i}`}>
                    <Card className="p-4 sm:p-5">
                      <div className="flex flex-wrap items-center gap-2">
                        <MatchBadge match={hit.match} />
                        {hit.sources.map((s) => (
                          <Badge key={s} tone="grey">
                            {s}
                          </Badge>
                        ))}
                        <span className="ml-auto text-xs text-muted tabular-nums" title="Relevance score">
                          score {hit.score.toFixed(3)}
                        </span>
                      </div>
                      <p className="mt-2 text-sm">
                        <Link href={docHref} className="link break-all">
                          {hit.document_name}
                        </Link>
                        {hit.page_number && <span className="text-muted"> · page {hit.page_number}</span>}
                      </p>
                      <p className="mt-1.5 line-clamp-4 text-sm leading-relaxed break-words whitespace-pre-line text-ink">
                        <Highlighted text={hit.snippet} />
                      </p>
                      {inv && (
                        <Link
                          href={`/invoices/${inv.id}`}
                          className="mt-3 inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-1 rounded-lg bg-cream px-3 py-1.5 text-xs ring-1 ring-line hover:ring-accent"
                        >
                          <Receipt className="size-3.5 text-accent-strong" aria-hidden />
                          <span className="font-semibold text-primary-dark">{inv.invoice_number || "No number"}</span>
                          {inv.supplier_name && <span className="truncate text-muted">{inv.supplier_name}</span>}
                          {inv.invoice_date && <span className="text-muted">{formatDate(inv.invoice_date)}</span>}
                          <span className="font-semibold text-ink tabular-nums">{formatMoney(inv.total, inv.currency)}</span>
                          <ReviewBadge status={inv.review_status} />
                        </Link>
                      )}
                    </Card>
                  </li>
                );
              })}
            </ol>
          )}
        </section>
      )}
    </>
  );
}
