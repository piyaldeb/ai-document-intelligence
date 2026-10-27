"use client";

import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { formatNumber } from "@/lib/format";
import { Button, cn } from "./ui";

/**
 * In-page confirmation (no window.confirm): the trigger button turns into
 * "<question> [Confirm] [Cancel]" in place.
 */
export function ConfirmButton({
  label,
  icon,
  question = "Are you sure?",
  confirmLabel = "Confirm",
  onConfirm,
  disabled,
  disabledReason,
  variant = "secondary",
  confirmVariant = "danger",
  size = "sm",
  className,
}: {
  label: string;
  icon?: ReactNode;
  question?: string;
  confirmLabel?: string;
  onConfirm: () => Promise<unknown> | void;
  disabled?: boolean;
  disabledReason?: string;
  variant?: "secondary" | "ghost" | "danger" | "navy";
  confirmVariant?: "danger" | "primary" | "navy";
  size?: "sm" | "md";
  className?: string;
}) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  function cancel() {
    setAsking(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  }

  async function confirm() {
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
      setAsking(false);
    }
  }

  if (!asking) {
    return (
      <Button
        ref={triggerRef}
        variant={variant}
        size={size}
        icon={icon}
        className={className}
        disabled={disabled}
        title={disabled ? disabledReason : undefined}
        onClick={() => setAsking(true)}
      >
        {label}
      </Button>
    );
  }
  return (
    <span
      className="inline-flex flex-wrap items-center gap-1.5 rounded-lg bg-red-50 px-2 py-1 ring-1 ring-red-200"
      role="group"
      aria-label={question}
      onKeyDown={(e) => {
        if (e.key === "Escape") cancel();
      }}
    >
      <span className="text-xs font-medium text-red-900">{question}</span>
      <Button variant={confirmVariant} size="sm" loading={busy} onClick={confirm} autoFocus>
        {confirmLabel}
      </Button>
      <Button variant="ghost" size="sm" disabled={busy} onClick={cancel}>
        Cancel
      </Button>
    </span>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
  label = "items",
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
  label?: string;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav
      aria-label="Pagination"
      className="flex flex-col items-center justify-between gap-2 border-t border-line px-4 py-3 text-sm text-muted sm:flex-row sm:px-5"
    >
      <p>
        Showing <span className="font-semibold text-ink">{formatNumber(from)}</span>–
        <span className="font-semibold text-ink">{formatNumber(to)}</span> of{" "}
        <span className="font-semibold text-ink">{formatNumber(total)}</span> {label}
      </p>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          icon={<ChevronLeft className="size-3.5" aria-hidden />}
        >
          Previous
        </Button>
        <span aria-current="page" className="px-1 text-xs">
          Page {formatNumber(page)} of {formatNumber(pages)}
        </span>
        <Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
          <ChevronRight className="size-3.5" aria-hidden />
        </Button>
      </div>
    </nav>
  );
}

export interface TabDef {
  id: string;
  label: ReactNode;
  count?: number;
}

/** Accessible tabs (roving focus with arrow keys); panels are rendered by the caller. */
export function Tabs({
  tabs,
  active,
  onChange,
  label,
  idBase,
}: {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
  label: string;
  idBase?: string;
}) {
  const auto = useId();
  const base = idBase ?? auto;
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKey(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = -1;
    if (e.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    if (next < 0) return;
    e.preventDefault();
    onChange(tabs[next].id);
    refs.current[next]?.focus();
  }

  return (
    <div className="relative overflow-x-auto overflow-y-hidden border-b border-line">
      <div role="tablist" aria-label={label} className="flex min-w-max gap-1 px-2 sm:px-3">
        {tabs.map((t, i) => {
          const selected = t.id === active;
          return (
            <button
              key={t.id}
              ref={(el) => {
                refs.current[i] = el;
              }}
              id={`${base}-tab-${t.id}`}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={`${base}-panel-${t.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(t.id)}
              onKeyDown={(e) => onKey(e, i)}
              className={cn(
                "relative flex items-center gap-1.5 border-b-2 px-3 py-3 text-sm font-medium whitespace-nowrap transition-colors",
                selected
                  ? "border-accent text-primary-dark"
                  : "border-transparent text-muted hover:border-primary-200 hover:text-primary-dark",
              )}
            >
              {t.label}
              {t.count !== undefined && (
                <span
                  className={cn(
                    "rounded-full px-1.5 py-0.5 text-[0.7rem] leading-none font-semibold",
                    selected ? "bg-accent-soft text-accent-strong" : "bg-slate-100 text-slate-600",
                  )}
                >
                  {formatNumber(t.count)}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function TabPanel({
  id,
  active,
  idBase,
  children,
  className,
}: {
  id: string;
  active: string;
  idBase: string;
  children: ReactNode;
  className?: string;
}) {
  if (id !== active) return null;
  return (
    <div
      role="tabpanel"
      id={`${idBase}-panel-${id}`}
      aria-labelledby={`${idBase}-tab-${id}`}
      tabIndex={0}
      className={cn("focus-visible:outline-offset-[-2px]", className)}
    >
      {children}
    </div>
  );
}

/** Segmented single-choice control (radio group semantics). */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  name,
}: {
  options: { value: T; label: string; hint?: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  name: string;
}) {
  return (
    <fieldset className="min-w-0">
      <legend className="sr-only">{label}</legend>
      <div className="inline-flex flex-wrap rounded-lg border border-line bg-slate-50 p-0.5">
        {options.map((o) => {
          const checked = o.value === value;
          return (
            <label
              key={o.value}
              title={o.hint}
              className={cn(
                "relative cursor-pointer rounded-md px-3 py-1.5 text-sm font-medium transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent",
                checked ? "bg-white text-primary-dark shadow-xs ring-1 ring-line" : "text-muted hover:text-primary-dark",
              )}
            >
              <input
                type="radio"
                name={name}
                value={o.value}
                checked={checked}
                onChange={() => onChange(o.value)}
                className="sr-only"
              />
              {o.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
