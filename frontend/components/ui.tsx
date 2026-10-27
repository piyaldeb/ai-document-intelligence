import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { CircleAlert, Inbox, LoaderCircle, RefreshCw } from "lucide-react";

export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/* ----------------------------------------------------------------------------- Buttons */

type Variant = "primary" | "navy" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  // Amber with dark label text: 5.3:1 contrast (white on #d97706 would only be 3.2:1).
  primary: "bg-accent text-ink hover:bg-accent-light border border-accent shadow-xs",
  navy: "bg-primary text-white hover:bg-primary-dark border border-primary shadow-xs",
  secondary: "bg-white text-primary-dark border border-line hover:border-primary-200 hover:bg-primary-50 shadow-xs",
  danger: "bg-red-700 text-white hover:bg-red-800 border border-red-700 shadow-xs",
  ghost: "bg-transparent text-primary hover:bg-primary-50 border border-transparent",
};
const SIZES: Record<Size, string> = {
  sm: "h-8 px-2.5 text-xs gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
};

export function buttonClass(variant: Variant = "secondary", size: Size = "md", extra?: string): string {
  return cn(
    "inline-flex shrink-0 items-center justify-center rounded-lg font-semibold whitespace-nowrap transition-colors",
    "disabled:cursor-not-allowed disabled:opacity-55",
    VARIANTS[variant],
    SIZES[size],
    extra,
  );
}

interface ButtonProps extends ComponentProps<"button"> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({ variant, size, loading, icon, className, children, disabled, type, ...rest }: ButtonProps) {
  return (
    <button
      type={type ?? "button"}
      className={buttonClass(variant, size, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

interface ButtonLinkProps extends ComponentProps<typeof Link> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
}

export function ButtonLink({ variant, size, icon, className, children, ...rest }: ButtonLinkProps) {
  return (
    <Link className={buttonClass(variant, size, className)} {...rest}>
      {icon}
      {children}
    </Link>
  );
}

/* ----------------------------------------------------------------------------- Layout */

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-sm text-muted">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight break-words sm:text-[1.7rem]">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ className, children, ...rest }: ComponentProps<"section">) {
  return (
    <section className={cn("card", className)} {...rest}>
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  description,
  actions,
  id,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  id?: string;
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div className="min-w-0">
        <h2 id={id} className="text-base font-semibold">
          {title}
        </h2>
        {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Horizontal scroll container for wide tables (the page itself never scrolls sideways). */
export function TableWrap({ children, label }: { children: ReactNode; label?: string }) {
  return (
    // `relative` keeps absolutely-positioned descendants (e.g. sr-only text) inside the scroller.
    <div className="relative overflow-x-auto" role="region" aria-label={label} tabIndex={label ? 0 : undefined}>
      {children}
    </div>
  );
}

/* ----------------------------------------------------------------------------- Badges */

export type Tone = "grey" | "blue" | "green" | "amber" | "red" | "navy" | "violet";

const TONES: Record<Tone, string> = {
  grey: "bg-slate-100 text-slate-700 ring-slate-300/70",
  blue: "bg-blue-50 text-blue-800 ring-blue-200",
  green: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  amber: "bg-amber-50 text-amber-900 ring-amber-300/80",
  red: "bg-red-50 text-red-800 ring-red-200",
  navy: "bg-primary-50 text-primary-dark ring-primary-200",
  violet: "bg-violet-50 text-violet-800 ring-violet-200",
};

export function Badge({
  tone = "grey",
  children,
  className,
  icon,
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  icon?: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold whitespace-nowrap ring-1 ring-inset",
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

/* ----------------------------------------------------------------------------- Progress */

export function ProgressBar({
  value,
  label,
  tone = "blue",
  className,
}: {
  value: number;
  label: string;
  tone?: "blue" | "amber" | "green";
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  const bar = tone === "amber" ? "bg-accent" : tone === "green" ? "bg-emerald-600" : "bg-blue-600";
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-slate-200", className)}
    >
      <div className={cn("h-full rounded-full transition-[width] duration-500", bar)} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <span className="inline-flex items-center gap-2" role={label ? "status" : undefined}>
      <LoaderCircle className={cn("size-4 animate-spin text-primary", className)} aria-hidden />
      {label && <span className="text-sm text-muted">{label}</span>}
    </span>
  );
}

/* ----------------------------------------------------------------------------- States */

export function LoadingState({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex items-center justify-center px-4 py-12", className)} role="status" aria-live="polite">
      <LoaderCircle className="size-5 animate-spin text-primary" aria-hidden />
      <span className="ml-2 text-sm text-muted">{label}</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
  className,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-4 py-12 text-center", className)}>
      <div className="mb-3 flex size-11 items-center justify-center rounded-full bg-primary-50 text-primary">
        {icon ?? <Inbox className="size-5" aria-hidden />}
      </div>
      <p className="font-heading text-sm font-semibold text-primary-dark">{title}</p>
      {description && <div className="mt-1 max-w-md text-sm text-muted">{description}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title = "Something went wrong",
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
}) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className={cn("flex flex-col items-center justify-center px-4 py-10 text-center", className)} role="alert">
      <div className="mb-3 flex size-11 items-center justify-center rounded-full bg-red-50 text-red-700">
        <CircleAlert className="size-5" aria-hidden />
      </div>
      <p className="font-heading text-sm font-semibold text-red-800">{title}</p>
      <p className="mt-1 max-w-lg text-sm break-words text-muted">{message}</p>
      {onRetry && (
        <Button className="mt-4" size="sm" onClick={onRetry} icon={<RefreshCw className="size-3.5" aria-hidden />}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** Small inline alert used inside cards and forms. */
export function Alert({
  tone = "red",
  title,
  children,
  className,
  actions,
}: {
  tone?: "red" | "amber" | "blue" | "green";
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
  actions?: ReactNode;
}) {
  const styles = {
    red: "border-red-200 bg-red-50 text-red-900",
    amber: "border-amber-300 bg-amber-50 text-amber-950",
    blue: "border-blue-200 bg-blue-50 text-blue-950",
    green: "border-emerald-200 bg-emerald-50 text-emerald-950",
  }[tone];
  return (
    <div className={cn("rounded-lg border px-3.5 py-3 text-sm", styles, className)} role={tone === "red" ? "alert" : "status"}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 break-words">
          {title && <p className="font-semibold">{title}</p>}
          {children && <div className={title ? "mt-0.5" : undefined}>{children}</div>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------------------- Misc */

export function Stat({
  label,
  value,
  hint,
  icon,
  accent,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  accent?: boolean;
}) {
  return (
    <div className={cn("card flex min-w-0 flex-col gap-1 p-4", accent && "border-accent/50 bg-cream")}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold tracking-wide text-muted uppercase">{label}</span>
        {icon && <span className="text-primary/70">{icon}</span>}
      </div>
      <div className="font-heading text-2xl font-semibold text-primary-dark">{value}</div>
      {hint && <div className="text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function KeyValue({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-semibold tracking-wide text-muted uppercase">{label}</dt>
      <dd className="mt-0.5 text-sm break-words text-ink">{children}</dd>
    </div>
  );
}

export function VisuallyHidden({ children }: { children: ReactNode }) {
  return <span className="sr-only">{children}</span>;
}
