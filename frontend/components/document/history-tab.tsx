import { CircleCheck, CircleX, Info, LoaderCircle, Activity } from "lucide-react";
import { formatDateTime, formatDuration, formatTime } from "@/lib/format";
import { stageLabel } from "@/lib/labels";
import type { EventOut } from "@/lib/types";
import { Badge, EmptyState, cn } from "@/components/ui";

interface Row {
  event: EventOut;
  startedAt: string | null;
  running: boolean;
}

/** Collapse "started" events that have a matching completed/failed event into one row. */
function toRows(events: EventOut[]): Row[] {
  const rows: Row[] = [];
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    if (e.status === "started") {
      const end = events.slice(i + 1).find(
        (x) => x.attempt === e.attempt && x.stage === e.stage && (x.status === "completed" || x.status === "failed"),
      );
      if (!end) rows.push({ event: e, startedAt: e.created_at, running: true });
      continue;
    }
    const start = [...events.slice(0, i)]
      .reverse()
      .find((x) => x.attempt === e.attempt && x.stage === e.stage && x.status === "started");
    rows.push({ event: e, startedAt: start?.created_at ?? null, running: false });
  }
  return rows;
}

function StatusIcon({ status, running }: { status: string; running: boolean }) {
  if (running) return <LoaderCircle className="size-4 animate-spin text-blue-700" aria-hidden />;
  if (status === "completed") return <CircleCheck className="size-4 text-emerald-700" aria-hidden />;
  if (status === "failed") return <CircleX className="size-4 text-red-700" aria-hidden />;
  return <Info className="size-4 text-primary" aria-hidden />;
}

export function HistoryTab({ events, active }: { events: EventOut[]; active: boolean }) {
  if (!events.length) {
    return (
      <EmptyState
        icon={<Activity className="size-5" aria-hidden />}
        title="No processing events yet"
        description={active ? "The document is waiting for a worker." : "Nothing has been recorded for this document."}
      />
    );
  }
  const attempts = [...new Set(events.map((e) => e.attempt))].sort((a, b) => b - a);
  return (
    <div className="space-y-6 p-4 sm:p-5">
      {attempts.map((attempt) => {
        const evs = events.filter((e) => e.attempt === attempt);
        const rows = toRows(evs);
        const failed = evs.some((e) => e.status === "failed");
        const total = evs.reduce((n, e) => n + (e.status !== "started" ? (e.duration_ms ?? 0) : 0), 0);
        return (
          <section key={attempt} aria-labelledby={`attempt-${attempt}`}>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <h3 id={`attempt-${attempt}`} className="text-sm font-semibold">
                Attempt {attempt}
              </h3>
              {failed ? <Badge tone="red">Failed</Badge> : attempt === attempts[0] && active ? <Badge tone="blue">Running</Badge> : <Badge tone="green">Finished</Badge>}
              <span className="text-xs text-muted">
                {formatDateTime(evs[0]?.created_at)} · stage time {formatDuration(total)}
              </span>
            </div>
            <ol className="relative ml-2 border-l border-line">
              {rows.map(({ event: e, running, startedAt }) => (
                <li key={e.id} className="relative pb-4 pl-6 last:pb-0">
                  <span className="absolute top-0.5 -left-[9px] flex size-[18px] items-center justify-center rounded-full bg-white">
                    <StatusIcon status={e.status} running={running} />
                  </span>
                  <div className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
                    <p className="text-sm">
                      <span className="font-semibold text-ink">{stageLabel(e.stage)}</span>{" "}
                      <span
                        className={cn(
                          "text-xs font-medium",
                          running ? "text-blue-800" : e.status === "failed" ? "text-red-800" : e.status === "completed" ? "text-emerald-800" : "text-muted",
                        )}
                      >
                        {running ? "running" : e.status}
                      </span>
                      <span className="ml-2 font-mono text-[0.7rem] text-muted">{e.stage}</span>
                    </p>
                    <p className="shrink-0 text-xs text-muted tabular-nums">
                      {e.duration_ms !== null && <span className="mr-2 font-semibold text-ink">{formatDuration(e.duration_ms)}</span>}
                      <time dateTime={e.created_at} title={formatDateTime(e.created_at)}>
                        {startedAt && !running ? `${formatTime(startedAt)} → ${formatTime(e.created_at)}` : formatTime(e.created_at)}
                      </time>
                    </p>
                  </div>
                  {e.message && (
                    <p
                      className={cn(
                        "mt-1 rounded-md px-2 py-1 text-xs break-words whitespace-pre-wrap",
                        e.status === "failed" ? "bg-red-50 text-red-900" : "bg-slate-50 text-muted",
                      )}
                    >
                      {e.message}
                    </p>
                  )}
                </li>
              ))}
            </ol>
          </section>
        );
      })}
    </div>
  );
}
