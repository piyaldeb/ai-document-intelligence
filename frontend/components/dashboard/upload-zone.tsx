"use client";

import Link from "next/link";
import { useRef, useState, type DragEvent } from "react";
import { CircleCheck, CircleX, CloudUpload, Copy, Trash, Upload, X } from "lucide-react";
import { ApiError, errorMessage, isAbortError, uploadFiles } from "@/lib/api";
import { formatBytes, pluralize } from "@/lib/format";
import { ACCEPT_ATTR, ACCEPTED_EXTENSIONS, extensionOf, isAcceptedFile } from "@/lib/labels";
import type { UploadResult } from "@/lib/types";
import { useToast } from "@/components/toast";
import { Alert, Button, Card, CardHeader, ProgressBar, cn } from "@/components/ui";
import { FileTypeIcon } from "@/components/badges";

/**
 * One file per request: stays within serverless request-size limits (e.g. Cloud Run 32 MiB) and,
 * when the backend processes inline, each file finishes and reports independently.
 */
const BATCH_FILES = 1;
const BATCH_BYTES = 30 * 1024 * 1024;

interface Staged {
  key: string;
  file: File;
  supported: boolean;
}

type Phase = "select" | "uploading" | "done";

function batchesOf(files: File[]): File[][] {
  const out: File[][] = [];
  let cur: File[] = [];
  let bytes = 0;
  for (const f of files) {
    if (cur.length && (cur.length >= BATCH_FILES || bytes + f.size > BATCH_BYTES)) {
      out.push(cur);
      cur = [];
      bytes = 0;
    }
    cur.push(f);
    bytes += f.size;
  }
  if (cur.length) out.push(cur);
  return out;
}

function kindFor(name: string): string {
  const ext = extensionOf(name);
  if ([".jpg", ".jpeg", ".png", ".tif", ".tiff"].includes(ext)) return "image";
  if ([".xlsx", ".xls", ".csv"].includes(ext)) return ext.slice(1);
  return "pdf";
}

export function UploadZone({ onUploaded }: { onUploaded: (results: UploadResult[]) => void }) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const cancelledRef = useRef(false);
  const counter = useRef(0);
  const [staged, setStaged] = useState<Staged[]>([]);
  const [phase, setPhase] = useState<Phase>("select");
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [batchInfo, setBatchInfo] = useState<{ index: number; count: number } | null>(null);
  const [results, setResults] = useState<UploadResult[]>([]);
  const [fatal, setFatal] = useState<string | null>(null);

  function addFiles(list: FileList | File[] | null) {
    if (!list) return;
    const incoming = Array.from(list);
    if (!incoming.length) return;
    setStaged((prev) => {
      const seen = new Set(prev.map((s) => `${s.file.name}|${s.file.size}|${s.file.lastModified}`));
      const next = [...prev];
      for (const file of incoming) {
        const sig = `${file.name}|${file.size}|${file.lastModified}`;
        if (seen.has(sig)) continue;
        seen.add(sig);
        next.push({ key: `f${counter.current++}`, file, supported: isAcceptedFile(file.name) });
      }
      return next;
    });
    if (phase === "done") {
      setPhase("select");
      setResults([]);
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    if (phase === "uploading") return;
    addFiles(e.dataTransfer.files);
  }

  const supported = staged.filter((s) => s.supported);
  const unsupported = staged.filter((s) => !s.supported);
  const totalBytes = supported.reduce((n, s) => n + s.file.size, 0);

  async function startUpload() {
    if (!supported.length) return;
    const files = supported.map((s) => s.file);
    const batches = batchesOf(files);
    const out: UploadResult[] = unsupported.map((s) => ({
      filename: s.file.name,
      accepted: false,
      document_id: null,
      duplicate_of: null,
      error: `Unsupported file type '${extensionOf(s.file.name) || "none"}'`,
    }));
    cancelledRef.current = false;
    setPhase("uploading");
    setFatal(null);
    setProgress(0);
    let doneBytes = 0;
    for (let i = 0; i < batches.length; i++) {
      if (cancelledRef.current) break;
      const batch = batches[i];
      const batchBytes = batch.reduce((n, f) => n + f.size, 0);
      setBatchInfo({ index: i + 1, count: batches.length });
      const handle = uploadFiles(batch, (loaded, total) => {
        const frac = total ? loaded / total : 0;
        setProgress(totalBytes ? (doneBytes + frac * batchBytes) / totalBytes : frac);
      });
      abortRef.current = handle.abort;
      try {
        const res = await handle.promise;
        out.push(...res.results);
      } catch (err) {
        if (isAbortError(err)) {
          cancelledRef.current = true;
          break;
        }
        const msg = errorMessage(err);
        if (err instanceof ApiError && err.status === 0) {
          setFatal(msg);
          break;
        }
        out.push(
          ...batch.map((f) => ({ filename: f.name, accepted: false, document_id: null, duplicate_of: null, error: msg })),
        );
      } finally {
        abortRef.current = null;
      }
      doneBytes += batchBytes;
      setProgress(totalBytes ? doneBytes / totalBytes : 1);
    }
    setBatchInfo(null);
    setResults(out);
    setPhase("done");
    setStaged([]);
    const accepted = out.filter((r) => r.accepted).length;
    if (accepted) {
      toast.success(`${pluralize(accepted, "document")} queued for processing`);
      onUploaded(out);
    } else if (cancelledRef.current) {
      toast.info("Upload cancelled");
    }
  }

  function reset() {
    setStaged([]);
    setResults([]);
    setFatal(null);
    setProgress(0);
    setPhase("select");
  }

  const accepted = results.filter((r) => r.accepted);
  const rejected = results.filter((r) => !r.accepted);

  return (
    <Card aria-labelledby="upload-title">
      <CardHeader
        id="upload-title"
        title="Upload documents"
        description="Invoices, receipts, scanned PDFs, images and spreadsheets. Drop many at once."
      />
      <div className="p-4 sm:p-5">
        <div
          onDragEnter={(e) => {
            e.preventDefault();
            if (phase !== "uploading") setDragging(true);
          }}
          onDragOver={(e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = phase === "uploading" ? "none" : "copy";
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
          }}
          onDrop={onDrop}
          className={cn(
            "flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors",
            dragging ? "border-accent bg-accent-soft" : "border-primary-200 bg-cream",
            phase === "uploading" && "opacity-70",
          )}
        >
          <CloudUpload className={cn("size-9", dragging ? "text-accent-strong" : "text-primary/70")} aria-hidden />
          <p className="mt-2 font-heading text-sm font-semibold text-primary-dark">
            {dragging ? "Drop to add files" : "Drag & drop files here"}
          </p>
          <p className="mt-1 text-xs text-muted">
            {ACCEPTED_EXTENSIONS.map((e) => e.slice(1).toUpperCase()).join(" · ")}
          </p>
          <Button
            className="mt-4"
            variant="navy"
            onClick={() => inputRef.current?.click()}
            disabled={phase === "uploading"}
            icon={<Upload className="size-4" aria-hidden />}
          >
            Choose files
          </Button>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPT_ATTR}
            hidden
            onChange={(e) => {
              addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {staged.length > 0 && phase !== "uploading" && (
          <div className="mt-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium text-ink">
                {pluralize(supported.length, "file")} ready ({formatBytes(totalBytes)})
                {unsupported.length > 0 && (
                  <span className="text-red-700"> · {unsupported.length} unsupported (will be skipped)</span>
                )}
              </p>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={() => setStaged([])} icon={<Trash className="size-3.5" aria-hidden />}>
                  Clear
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={startUpload}
                  disabled={!supported.length}
                  icon={<Upload className="size-3.5" aria-hidden />}
                >
                  Upload {supported.length ? pluralize(supported.length, "file") : ""}
                </Button>
              </div>
            </div>
            <ul className="max-h-56 divide-y divide-line overflow-y-auto rounded-lg border border-line">
              {staged.map((s) => (
                <li key={s.key} className="flex items-center gap-2 px-3 py-2 text-sm">
                  <FileTypeIcon type={kindFor(s.file.name)} />
                  <span className="min-w-0 flex-1 truncate" title={s.file.name}>
                    {s.file.name}
                  </span>
                  {!s.supported && (
                    <span className="text-xs font-medium text-red-700">Unsupported type</span>
                  )}
                  <span className="text-xs text-muted tabular-nums">{formatBytes(s.file.size)}</span>
                  <button
                    type="button"
                    onClick={() => setStaged((prev) => prev.filter((x) => x.key !== s.key))}
                    className="rounded p-1 text-muted hover:bg-slate-100 hover:text-ink"
                    aria-label={`Remove ${s.file.name}`}
                  >
                    <X className="size-3.5" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {phase === "uploading" && (
          <div className="mt-4" aria-live="polite">
            <div className="mb-1.5 flex items-center justify-between gap-2 text-sm">
              <span className="font-medium text-ink">
                Uploading {pluralize(supported.length, "file")} ({formatBytes(totalBytes)})
                {batchInfo && batchInfo.count > 1 && (
                  <span className="text-muted">
                    {" "}
                    · batch {batchInfo.index} of {batchInfo.count}
                  </span>
                )}
              </span>
              <span className="font-semibold text-primary tabular-nums">{Math.round(progress * 100)}%</span>
            </div>
            <ProgressBar value={progress * 100} label="Upload progress" tone="amber" className="h-2" />
            <div className="mt-2 flex justify-end">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  cancelledRef.current = true;
                  abortRef.current?.();
                }}
              >
                Cancel upload
              </Button>
            </div>
          </div>
        )}

        {fatal && (
          <Alert className="mt-4" title="Upload interrupted">
            {fatal}
          </Alert>
        )}

        {phase === "done" && results.length > 0 && (
          <div className="mt-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium text-ink">
                <span className="text-emerald-800">{accepted.length} accepted</span>
                {rejected.length > 0 && <span className="text-red-700"> · {rejected.length} rejected</span>}
              </p>
              <Button size="sm" variant="ghost" onClick={reset}>
                Dismiss
              </Button>
            </div>
            <ul className="max-h-72 divide-y divide-line overflow-y-auto rounded-lg border border-line">
              {results.map((r, i) => (
                <li key={`${r.filename}-${i}`} className="flex items-start gap-2 px-3 py-2 text-sm">
                  {r.accepted ? (
                    <CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-700" aria-label="Accepted" />
                  ) : (
                    <CircleX className="mt-0.5 size-4 shrink-0 text-red-700" aria-label="Rejected" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium" title={r.filename}>
                      {r.accepted && r.document_id ? (
                        <Link href={`/documents/${r.document_id}`} className="link">
                          {r.filename}
                        </Link>
                      ) : (
                        r.filename
                      )}
                    </p>
                    {r.accepted ? (
                      <p className="text-xs text-muted">Queued for processing</p>
                    ) : (
                      <p className="text-xs break-words text-red-800">{r.error ?? "Rejected"}</p>
                    )}
                    {r.duplicate_of && (
                      <p className="mt-1 inline-flex flex-wrap items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-950 ring-1 ring-amber-200">
                        <Copy className="size-3" aria-hidden />
                        Identical file was uploaded before — duplicate of{" "}
                        <Link href={`/documents/${r.duplicate_of}`} className="link">
                          earlier document
                        </Link>
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
