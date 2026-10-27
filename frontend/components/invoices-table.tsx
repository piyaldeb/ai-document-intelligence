"use client";

import Link from "next/link";
import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink } from "lucide-react";
import { formatDate, formatMoney } from "@/lib/format";
import type { InvoiceSummary } from "@/lib/types";
import { IssueCounts, ReviewBadge } from "./badges";
import { TableWrap, cn } from "./ui";

export type SortKey = "created_desc" | "date_desc" | "date_asc" | "total_desc" | "total_asc" | "issues_desc";

/** Where an invoice came from inside its document: page range or sheet/rows. */
export function sourceLabel(inv: Pick<InvoiceSummary, "page_start" | "page_end" | "source_ref">): string {
  const ref = inv.source_ref ?? {};
  if (typeof ref.sheet === "string") {
    const rows = Array.isArray(ref.rows)
      ? ref.rows[0] === ref.rows[1]
        ? ` row ${ref.rows[0]}`
        : ` rows ${ref.rows[0]}–${ref.rows[1]}`
      : "";
    return `Sheet “${ref.sheet}”${rows}`;
  }
  if (inv.page_start) {
    return inv.page_end && inv.page_end !== inv.page_start ? `Pages ${inv.page_start}–${inv.page_end}` : `Page ${inv.page_start}`;
  }
  return "—";
}

function SortHeader({
  label,
  asc,
  desc,
  sort,
  onSort,
  align = "left",
}: {
  label: string;
  asc?: SortKey;
  desc: SortKey;
  sort?: SortKey;
  onSort?: (s: SortKey) => void;
  align?: "left" | "right";
}) {
  const active = sort === desc || (asc && sort === asc);
  const direction = sort === desc ? "descending" : asc && sort === asc ? "ascending" : undefined;
  if (!onSort) {
    return (
      <th scope="col" className={align === "right" ? "text-right" : undefined}>
        {label}
      </th>
    );
  }
  const next: SortKey = sort === desc && asc ? asc : desc;
  const Icon = direction === "descending" ? ArrowDown : direction === "ascending" ? ArrowUp : ArrowUpDown;
  return (
    <th scope="col" aria-sort={direction ?? "none"} className={align === "right" ? "text-right" : undefined}>
      <button
        type="button"
        onClick={() => onSort(next)}
        className={cn(
          "inline-flex items-center gap-1 rounded uppercase hover:text-primary-dark",
          active && "text-primary-dark",
          align === "right" && "flex-row-reverse",
        )}
      >
        {label}
        <Icon className={cn("size-3.5", !active && "opacity-50")} aria-hidden />
        <span className="sr-only">
          {direction ? `, sorted ${direction}. ` : ""}Activate to sort {next.endsWith("asc") ? "ascending" : "descending"}
        </span>
      </button>
    </th>
  );
}

export function InvoicesTable({
  invoices,
  sort,
  onSort,
  showSource,
  showDocumentLink = true,
}: {
  invoices: InvoiceSummary[];
  sort?: SortKey;
  onSort?: (s: SortKey) => void;
  showSource?: boolean;
  showDocumentLink?: boolean;
}) {
  return (
    <TableWrap label="Invoices">
      <table className="table-base min-w-[900px]">
        <thead>
          <tr>
            <th scope="col">Invoice #</th>
            <SortHeader label="Date" desc="date_desc" asc="date_asc" sort={sort} onSort={onSort} />
            <th scope="col">Supplier</th>
            <th scope="col">Customer</th>
            <SortHeader label="Total" desc="total_desc" asc="total_asc" sort={sort} onSort={onSort} align="right" />
            <th scope="col">Status</th>
            <SortHeader label="Issues" desc="issues_desc" sort={sort} onSort={onSort} />
            {showSource && <th scope="col">Source</th>}
            {showDocumentLink && (
              <th scope="col">
                <span className="sr-only">Document</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {invoices.map((inv) => (
            <tr key={inv.id}>
              <td className="whitespace-nowrap">
                <Link href={`/invoices/${inv.id}`} className="link">
                  {inv.invoice_number || <span className="text-muted italic">No number</span>}
                </Link>
              </td>
              <td className="whitespace-nowrap">{formatDate(inv.invoice_date)}</td>
              <td className="max-w-[14rem] truncate" title={inv.supplier_name ?? undefined}>
                {inv.supplier_name || <span className="text-muted">—</span>}
              </td>
              <td className="max-w-[12rem] truncate" title={inv.customer_name ?? undefined}>
                {inv.customer_name || <span className="text-muted">—</span>}
              </td>
              <td className="text-right font-semibold whitespace-nowrap tabular-nums">
                {formatMoney(inv.total, inv.currency)}
              </td>
              <td>
                <ReviewBadge status={inv.review_status} />
              </td>
              <td>
                <IssueCounts errors={inv.error_count} warnings={inv.warning_count} />
              </td>
              {showSource && <td className="whitespace-nowrap text-muted">{sourceLabel(inv)}</td>}
              {showDocumentLink && (
                <td className="text-right">
                  <Link
                    href={`/documents/${inv.document_id}`}
                    className="inline-flex items-center gap-1 rounded text-xs font-medium text-muted hover:text-primary"
                    title="Open source document"
                  >
                    <ExternalLink className="size-3.5" aria-hidden />
                    <span className="sr-only">Open source document for invoice {inv.invoice_number ?? ""}</span>
                  </Link>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}
