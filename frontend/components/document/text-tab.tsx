"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Check, ChevronLeft, ChevronRight, Copy, ScanText, TriangleAlert } from "lucide-react";
import { api, errorMessage, isAbortError } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type { DocumentDetail, PageOut } from "@/lib/types";
import { MethodBadge } from "@/components/badges";
import { Badge, Button, EmptyState, ErrorState, LoadingState, cn } from "@/components/ui";

const CHUNK = 20; // pages fetched per /pages request
const SELECT_LIMIT = 300; // above this, a numeric "go to page" input replaces the dropdown

export function TextTab({
  doc,
  page,
  onPage,
}: {
  doc: DocumentDetail;
  page: number | null;
  onPage: (p: number) => void;
}) {
  const pages = doc.pages;
  const numbers = pages.map((p) => p.page_number);
  const current = page && numbers.includes(page) ? page : (numbers[0] ?? null);
  const index = current === null ? -1 : numbers.indexOf(current);
  const meta = index >= 0 ? pages[index] : null;
  const isSheet = pages.some((p) => p.sheet_name);

  const [cache, setCache] = useState<Record<number, PageOut>>({});
  const [failure, setFailure] = useState<{ chunk: number; error: Error } | null>(null);
  const [nonce, setNonce] = useState(0);
  const [copied, setCopied] = useState(false);
  const [goto, setGoto] = useState("");

  const chunkStart = current === null ? null : Math.floor((current - 1) / CHUNK) * CHUNK + 1;
  const loaded = current !== null && cache[current] !== undefined;

  useEffect(() => {
    if (chunkStart === null || loaded) return;
    const ctrl = new AbortController();
    api<PageOut[]>(`/api/documents/${doc.id}/pages?page_from=${chunkStart}&page_to=${chunkStart + CHUNK - 1}`, {
      signal: ctrl.signal,
    }).then(
      (rows) => {
        setFailure(null);
        setCache((prev) => {
          const next = { ...prev };
          for (const r of rows) next[r.page_number] = r;
          return next;
        });
      },
      (err: unknown) => {
        if (!isAbortError(err)) setFailure({ chunk: chunkStart, error: err instanceof Error ? err : new Error(String(err)) });
      },
    );
    return () => ctrl.abort();
  }, [doc.id, chunkStart, loaded, nonce]);

  if (!pages.length || current === null || !meta) {
    return (
      <EmptyState
        icon={<ScanText className="size-5" aria-hidden />}
        title="No extracted text"
        description={
          doc.status === "queued" || doc.status === "processing"
            ? "Text will appear here once extraction finishes."
            : "This document produced no pages or sheets."
        }
      />
    );
  }

  const text = cache[current];
  const error = failure && failure.chunk === chunkStart ? failure.error : null;
  const label = (p: (typeof pages)[number]) => (p.sheet_name ? `Sheet: ${p.sheet_name}` : `Page ${p.page_number}`);
  const ocr = meta.ocr_confidence;
  const invoicesHere = doc.invoices.filter(
    (inv) => inv.page_start !== null && inv.page_start <= current && current <= (inv.page_end ?? inv.page_start),
  );

  async function copyText() {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text.text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard not permitted */
    }
  }

  return (
    <div className="p-4 sm:p-5">
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex flex-wrap items-end gap-2">
          <Button
            size="sm"
            onClick={() => onPage(numbers[index - 1])}
            disabled={index <= 0}
            aria-label={isSheet ? "Previous sheet" : "Previous page"}
            icon={<ChevronLeft className="size-3.5" aria-hidden />}
          />
          {pages.length <= SELECT_LIMIT ? (
            <div>
              <label htmlFor="page-select" className="form-label">
                {isSheet ? "Sheet" : "Page"}
              </label>
              <select
                id="page-select"
                className="form-control h-8 w-auto max-w-[16rem] py-1"
                value={current}
                onChange={(e) => onPage(Number(e.target.value))}
              >
                {pages.map((p) => (
                  <option key={p.page_number} value={p.page_number}>
                    {label(p)}
                    {p.method === "ocr" ? " · OCR" : ""}
                    {p.warnings.length ? " · ⚠" : ""}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <form
              className="flex items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                const n = Number(goto);
                if (numbers.includes(n)) onPage(n);
              }}
            >
              <div>
                <label htmlFor="page-goto" className="form-label">
                  Go to page (1–{formatNumber(numbers[numbers.length - 1])})
                </label>
                <input
                  id="page-goto"
                  type="number"
                  min={numbers[0]}
                  max={numbers[numbers.length - 1]}
                  className="form-control h-8 w-28 py-1"
                  value={goto}
                  placeholder={String(current)}
                  onChange={(e) => setGoto(e.target.value)}
                />
              </div>
              <Button size="sm" type="submit">
                Go
              </Button>
            </form>
          )}
          <Button
            size="sm"
            onClick={() => onPage(numbers[index + 1])}
            disabled={index >= numbers.length - 1}
            aria-label={isSheet ? "Next sheet" : "Next page"}
            icon={<ChevronRight className="size-3.5" aria-hidden />}
          />
          <span className="pb-1.5 text-xs text-muted">
            {index + 1} of {formatNumber(pages.length)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
          <MethodBadge method={meta.method} />
          {ocr !== null && (
            <Badge tone={ocr < 60 ? "red" : ocr < 80 ? "amber" : "green"} title="Mean OCR word confidence (0–100)">
              OCR confidence {Math.round(ocr)}/100
            </Badge>
          )}
          <span>{formatNumber(meta.char_count)} characters</span>
          <Button
            size="sm"
            variant="ghost"
            onClick={copyText}
            disabled={!text}
            icon={copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
          >
            {copied ? "Copied" : "Copy text"}
          </Button>
        </div>
      </div>

      {meta.warnings.length > 0 && (
        <ul className="mb-3 space-y-1 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950">
          {meta.warnings.map((w, i) => (
            <li key={i} className="flex items-start gap-2">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              <span className="break-words">{w}</span>
            </li>
          ))}
        </ul>
      )}

      {invoicesHere.length > 0 && (
        <p className="mb-3 flex flex-wrap items-center gap-1.5 text-xs text-muted">
          Invoices on this {isSheet ? "sheet" : "page"}:
          {invoicesHere.map((inv) => (
            <Link key={inv.id} href={`/invoices/${inv.id}`} className="rounded bg-primary-50 px-1.5 py-0.5 font-medium text-primary hover:underline">
              {inv.invoice_number || `#${inv.sequence}`}
            </Link>
          ))}
        </p>
      )}

      {error ? (
        <ErrorState title="Could not load page text" error={errorMessage(error)} onRetry={() => {
            setFailure(null);
            setNonce((n) => n + 1);
          }}
        />
      ) : !text ? (
        <LoadingState label={`Loading ${label(meta).toLowerCase()}…`} />
      ) : text.text.trim() ? (
        <pre
          className={cn(
            "max-h-[70vh] overflow-auto rounded-lg border border-line bg-slate-50 p-4 font-mono text-xs leading-relaxed whitespace-pre-wrap text-ink sm:text-[0.8rem]",
            "break-words",
          )}
          tabIndex={0}
          aria-label={`Extracted text of ${label(meta).toLowerCase()}`}
        >
          {text.text}
        </pre>
      ) : (
        <EmptyState title="No text on this page" description="The page is blank or OCR found no readable text." />
      )}
    </div>
  );
}
