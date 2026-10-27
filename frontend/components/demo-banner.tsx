"use client";

import { Info } from "lucide-react";
import { useEffect, useState } from "react";

type Health = { demo_mode?: boolean; demo_reset_hours?: number; max_upload_mb?: number; extraction_provider?: string };

const REPO = "https://github.com/piyaldeb/ai-document-intelligence";

/** Shown only on the public demo deployment (backend DEMO_MODE=true). */
export function DemoBanner() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/health", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((h: Health | null) => {
        if (!cancelled) setHealth(h);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (!health?.demo_mode) return null;
  return (
    <div className="border-b border-amber-300 bg-amber-50 text-ink" role="note" aria-label="Public demo notice">
      <div className="mx-auto flex max-w-7xl items-start gap-2 px-4 py-2 text-sm sm:px-6">
        <Info className="mt-0.5 size-4 shrink-0 text-amber-700" aria-hidden />
        <p>
          <strong className="font-semibold">Public demo.</strong> Sample documents are pre-loaded. Upload your own files
          (max {health.max_upload_mb ?? 15} MB each) — but nothing confidential: data is visible to other visitors and resets
          every {health.demo_reset_hours ?? 24} h. Extraction: <span className="font-medium">{health.extraction_provider}</span>.{" "}
          <a className="font-semibold text-primary underline underline-offset-2" href={`${REPO}/tree/main/eval/dataset`} target="_blank" rel="noreferrer">
            Sample files
          </a>{" "}
          ·{" "}
          <a className="font-semibold text-primary underline underline-offset-2" href="/api/docs" target="_blank" rel="noreferrer">
            API docs
          </a>{" "}
          ·{" "}
          <a className="font-semibold text-primary underline underline-offset-2" href={REPO} target="_blank" rel="noreferrer">
            Source code
          </a>
        </p>
      </div>
    </div>
  );
}
