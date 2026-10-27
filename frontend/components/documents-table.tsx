"use client";

import Link from "next/link";
import { Eye, RotateCcw, Trash } from "lucide-react";
import { formatBytes, formatDuration, formatNumber, formatRelative } from "@/lib/format";
import { fileTypeLabel, isActive, stageLabel } from "@/lib/labels";
import type { DocumentSummary } from "@/lib/types";
import { DocumentStatusBadge, FileTypeIcon } from "./badges";
import { ConfirmButton } from "./controls";
import { ButtonLink, Button, ProgressBar, TableWrap } from "./ui";

export function DocumentProgress({ doc }: { doc: Pick<DocumentSummary, "status" | "stage" | "progress"> }) {
  if (!isActive(doc.status)) return null;
  const pct = doc.status === "queued" ? 0 : doc.progress;
  return (
    <div className="mt-1.5 w-36 max-w-full">
      <ProgressBar value={pct} label={`Processing progress, ${stageLabel(doc.stage)}`} />
      <p className="mt-1 truncate text-xs text-muted">
        {stageLabel(doc.stage)}
        {doc.status === "processing" && <span className="tabular-nums"> · {pct}%</span>}
      </p>
    </div>
  );
}

export function DocumentsTable({
  documents,
  now,
  busyId,
  onReprocess,
  onDelete,
}: {
  documents: DocumentSummary[];
  now: number;
  busyId: string | null;
  onReprocess: (doc: DocumentSummary) => void;
  onDelete: (doc: DocumentSummary) => Promise<void>;
}) {
  return (
    <TableWrap label="Documents">
      <table className="table-base min-w-[880px]">
        <thead>
          <tr>
            <th scope="col">File</th>
            <th scope="col">Type</th>
            <th scope="col">Status</th>
            <th scope="col" className="text-right">
              Pages
            </th>
            <th scope="col" className="text-right">
              Invoices
            </th>
            <th scope="col" className="text-right">
              Processing time
            </th>
            <th scope="col">Uploaded</th>
            <th scope="col" className="text-right">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {documents.map((d) => (
            <tr key={d.id}>
              <td className="max-w-[18rem]">
                <div className="flex items-start gap-2">
                  <FileTypeIcon type={d.file_type} className="mt-0.5" />
                  <div className="min-w-0">
                    <Link href={`/documents/${d.id}`} className="link block truncate" title={d.original_filename}>
                      {d.original_filename}
                    </Link>
                    <span className="text-xs text-muted">
                      {formatBytes(d.size_bytes)}
                      {d.duplicate_of_id && (
                        <>
                          {" · "}
                          <Link href={`/documents/${d.duplicate_of_id}`} className="font-medium text-accent-strong hover:underline">
                            duplicate file
                          </Link>
                        </>
                      )}
                    </span>
                  </div>
                </div>
              </td>
              <td className="whitespace-nowrap text-muted">{fileTypeLabel(d.file_type)}</td>
              <td>
                <DocumentStatusBadge status={d.status} />
                <DocumentProgress doc={d} />
                {d.status === "failed" && d.error_code && (
                  <p className="mt-1 max-w-[14rem] truncate font-mono text-[0.7rem] text-red-800" title={d.error_message ?? d.error_code}>
                    {d.error_code}
                  </p>
                )}
              </td>
              <td className="text-right tabular-nums">{formatNumber(d.page_count)}</td>
              <td className="text-right tabular-nums">
                {isActive(d.status) && !d.invoice_count ? "—" : formatNumber(d.invoice_count)}
              </td>
              <td className="text-right whitespace-nowrap tabular-nums">{formatDuration(d.processing_ms)}</td>
              <td className="whitespace-nowrap text-muted" title={new Date(d.created_at).toLocaleString()}>
                {formatRelative(d.created_at, now)}
              </td>
              <td>
                <div className="flex flex-wrap items-center justify-end gap-1.5">
                  <ButtonLink
                    href={`/documents/${d.id}`}
                    size="sm"
                    variant="ghost"
                    icon={<Eye className="size-3.5" aria-hidden />}
                    aria-label={`Open ${d.original_filename}`}
                  >
                    Open
                  </ButtonLink>
                  {d.status === "failed" && (
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={busyId === d.id}
                      onClick={() => onReprocess(d)}
                      icon={<RotateCcw className="size-3.5" aria-hidden />}
                      aria-label={`Reprocess ${d.original_filename}`}
                    >
                      Reprocess
                    </Button>
                  )}
                  <ConfirmButton
                    label="Delete"
                    variant="ghost"
                    icon={<Trash className="size-3.5" aria-hidden />}
                    question="Delete document?"
                    confirmLabel="Delete"
                    disabled={d.status === "processing"}
                    disabledReason="Cannot delete while processing"
                    onConfirm={() => onDelete(d)}
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}
