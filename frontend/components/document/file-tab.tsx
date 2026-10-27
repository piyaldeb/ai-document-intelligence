import { Download, ExternalLink, FileSpreadsheet, FileImage } from "lucide-react";
import { formatBytes } from "@/lib/format";
import { isSpreadsheet } from "@/lib/labels";
import type { DocumentDetail } from "@/lib/types";
import { EmptyState, buttonClass } from "@/components/ui";

/** Browsers can render these inline; TIFF only works in Safari, so it is offered as a download. */
const INLINE_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"]);

export function FileTab({ doc }: { doc: DocumentDetail }) {
  const url = `/api/documents/${doc.id}/file`;
  const isPdf = doc.file_type === "pdf" && doc.mime_type === "application/pdf";
  const isImage = doc.file_type === "image" && INLINE_IMAGE_TYPES.has(doc.mime_type);
  const canOpen = isPdf || isImage;

  return (
    <div className="p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted">
          <span className="font-medium text-ink">{doc.original_filename}</span> · {doc.mime_type} · {formatBytes(doc.size_bytes)}
        </p>
        <div className="flex flex-wrap gap-2">
          {canOpen && (
            <a href={url} target="_blank" rel="noopener" className={buttonClass("secondary", "sm")}>
              <ExternalLink className="size-3.5" aria-hidden />
              Open in new tab
            </a>
          )}
          <a href={url} download={doc.original_filename} className={buttonClass("navy", "sm")}>
            <Download className="size-3.5" aria-hidden />
            Download original
          </a>
        </div>
      </div>

      {isPdf ? (
        <iframe
          src={url}
          title={`Preview of ${doc.original_filename}`}
          className="h-[75vh] min-h-[420px] w-full rounded-lg border border-line bg-slate-100"
        />
      ) : isImage ? (
        <div className="flex justify-center rounded-lg border border-line bg-slate-100 p-3">
          {/* eslint-disable-next-line @next/next/no-img-element -- authenticated same-origin proxy URL, not optimisable */}
          <img
            src={url}
            alt={`Original upload: ${doc.original_filename}`}
            className="max-h-[75vh] w-auto max-w-full rounded bg-white object-contain shadow-sm"
          />
        </div>
      ) : (
        <EmptyState
          icon={
            isSpreadsheet(doc.file_type) ? (
              <FileSpreadsheet className="size-5" aria-hidden />
            ) : (
              <FileImage className="size-5" aria-hidden />
            )
          }
          title={isSpreadsheet(doc.file_type) ? "Spreadsheets can't be previewed in the browser" : "Preview not available for this format"}
          description={
            isSpreadsheet(doc.file_type)
              ? "Download the original file, or read the extracted sheets in the “Extracted text” tab."
              : "Download the original file to view it. The extracted text is available in the “Extracted text” tab."
          }
        />
      )}
    </div>
  );
}
