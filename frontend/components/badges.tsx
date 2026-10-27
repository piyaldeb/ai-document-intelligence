import {
  CircleAlert,
  CircleCheck,
  CircleX,
  Clock,
  FileImage,
  FileSpreadsheet,
  FileText,
  Info,
  LoaderCircle,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { Badge, type Tone, cn } from "./ui";
import {
  DOCUMENT_STATUS_LABELS,
  RECON_STATUS_LABELS,
  REVIEW_STATUS_LABELS,
  isSpreadsheet,
  methodLabel,
} from "@/lib/labels";
import type { DocumentStatus, ReviewStatus, Severity } from "@/lib/types";

const DOC_TONES: Record<DocumentStatus, Tone> = {
  queued: "grey",
  processing: "blue",
  completed: "green",
  needs_review: "amber",
  failed: "red",
};

export function DocumentStatusBadge({ status }: { status: string }) {
  const s = status as DocumentStatus;
  const icon =
    s === "processing" ? (
      <LoaderCircle className="size-3 animate-spin" aria-hidden />
    ) : s === "queued" ? (
      <Clock className="size-3" aria-hidden />
    ) : s === "completed" ? (
      <CircleCheck className="size-3" aria-hidden />
    ) : s === "needs_review" ? (
      <TriangleAlert className="size-3" aria-hidden />
    ) : s === "failed" ? (
      <CircleX className="size-3" aria-hidden />
    ) : null;
  return (
    <Badge tone={DOC_TONES[s] ?? "grey"} icon={icon}>
      {DOCUMENT_STATUS_LABELS[s] ?? status}
    </Badge>
  );
}

const REVIEW_TONES: Record<ReviewStatus, Tone> = { ok: "green", needs_review: "amber", approved: "navy" };

export function ReviewBadge({ status }: { status: string }) {
  const s = status as ReviewStatus;
  const icon =
    s === "approved" ? (
      <ShieldCheck className="size-3" aria-hidden />
    ) : s === "needs_review" ? (
      <TriangleAlert className="size-3" aria-hidden />
    ) : (
      <CircleCheck className="size-3" aria-hidden />
    );
  return (
    <Badge tone={REVIEW_TONES[s] ?? "grey"} icon={icon}>
      {REVIEW_STATUS_LABELS[s] ?? status}
    </Badge>
  );
}

export function SeverityBadge({ severity }: { severity: Severity | string }) {
  if (severity === "error")
    return (
      <Badge tone="red" icon={<CircleAlert className="size-3" aria-hidden />}>
        Error
      </Badge>
    );
  if (severity === "warning")
    return (
      <Badge tone="amber" icon={<TriangleAlert className="size-3" aria-hidden />}>
        Warning
      </Badge>
    );
  return (
    <Badge tone="grey" icon={<Info className="size-3" aria-hidden />}>
      Info
    </Badge>
  );
}

/** Error / warning counters shown in invoice tables. */
export function IssueCounts({ errors, warnings }: { errors: number; warnings: number }) {
  if (!errors && !warnings) return <span className="text-xs text-muted">None</span>;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {errors > 0 && (
        <Badge tone="red" title={`${errors} validation error(s)`}>
          {errors} {errors === 1 ? "error" : "errors"}
        </Badge>
      )}
      {warnings > 0 && (
        <Badge tone="amber" title={`${warnings} warning(s)`}>
          {warnings} {warnings === 1 ? "warning" : "warnings"}
        </Badge>
      )}
    </span>
  );
}

/** Field confidence: green >= 0.85, amber >= 0.6, red below, grey when unknown. */
export function ConfidenceBadge({ value, verified }: { value: number | null | undefined; verified?: boolean }) {
  if (verified) {
    return (
      <Badge tone="navy" icon={<ShieldCheck className="size-3" aria-hidden />} title="Corrected by a reviewer">
        Verified
      </Badge>
    );
  }
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return (
      <Badge tone="grey" title="No confidence score">
        n/a
      </Badge>
    );
  }
  const tone: Tone = value >= 0.85 ? "green" : value >= 0.6 ? "amber" : "red";
  const label = value >= 0.85 ? "High" : value >= 0.6 ? "Medium" : "Low";
  return (
    <Badge tone={tone} title={`${label} extraction confidence`}>
      <span className="sr-only">Confidence </span>
      {Math.round(value * 100)}%
    </Badge>
  );
}

export function MethodBadge({ method }: { method: string }) {
  const tone: Tone = method === "ocr" ? "violet" : method === "spreadsheet" ? "green" : "blue";
  return <Badge tone={tone}>{methodLabel(method)}</Badge>;
}

export function MatchBadge({ match }: { match: string }) {
  const tone: Tone = match === "hybrid" ? "navy" : match === "semantic" ? "violet" : "blue";
  return <Badge tone={tone}>{match.charAt(0).toUpperCase() + match.slice(1)}</Badge>;
}

const RECON_TONES: Record<string, Tone> = {
  matched: "green",
  mismatch: "red",
  missing_in_left: "amber",
  missing_in_right: "amber",
};

export function ReconStatusBadge({ status }: { status: string }) {
  return <Badge tone={RECON_TONES[status] ?? "grey"}>{RECON_STATUS_LABELS[status] ?? status}</Badge>;
}

export function FileTypeIcon({ type, className }: { type: string; className?: string }) {
  const cls = cn("size-4 shrink-0", className);
  if (type === "image") return <FileImage className={cn(cls, "text-violet-700")} aria-hidden />;
  if (isSpreadsheet(type)) return <FileSpreadsheet className={cn(cls, "text-emerald-700")} aria-hidden />;
  return <FileText className={cn(cls, "text-red-700")} aria-hidden />;
}
