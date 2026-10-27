"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { ClipboardCheck, GitCompareArrows, LayoutDashboard, Menu, Receipt, ScanText, Search, X } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { providerLabel } from "@/lib/labels";
import type { Health } from "@/lib/types";
import { cn } from "./ui";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/invoices", label: "Invoices", icon: Receipt },
  { href: "/review", label: "Review queue", icon: ClipboardCheck },
  { href: "/search", label: "Search", icon: Search },
  { href: "/reconcile", label: "Cross-verify", icon: GitCompareArrows },
];

function isCurrent(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/documents");
  return pathname === href || pathname.startsWith(`${href}/`);
}

function HealthDot() {
  const { data, error, loading } = useApi<Health>("/api/health");
  const ok = !!data && data.status === "ok" && !error;
  const label = loading && !data ? "Checking API…" : ok ? `API online · ${providerLabel(data?.extraction_provider)}` : "API offline";
  return (
    <span className="hidden items-center gap-2 text-xs text-white/80 lg:inline-flex" title={label}>
      <span
        className={cn("size-2 rounded-full", loading && !data ? "bg-slate-300" : ok ? "bg-emerald-400" : "bg-red-400")}
        aria-hidden
      />
      {label}
    </span>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [lastPath, setLastPath] = useState(pathname);
  if (lastPath !== pathname) {
    // Close the mobile menu after navigation (state derived from props, no effect needed).
    setLastPath(pathname);
    setOpen(false);
  }

  return (
    <header className="sticky top-0 z-40 bg-primary text-white shadow-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 rounded-md font-heading text-lg font-semibold tracking-tight">
          <span className="flex size-8 items-center justify-center rounded-lg bg-accent text-ink">
            <ScanText className="size-4.5" aria-hidden />
          </span>
          DocIntel
        </Link>

        <nav aria-label="Main" className="ml-4 hidden md:block">
          <ul className="flex items-center gap-1">
            {NAV.map((item) => {
              const current = isCurrent(pathname, item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={current ? "page" : undefined}
                    className={cn(
                      "relative flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      current ? "bg-white/12 text-white" : "text-white/80 hover:bg-white/8 hover:text-white",
                    )}
                  >
                    <item.icon className="size-4" aria-hidden />
                    {item.label}
                    {current && <span className="absolute inset-x-3 -bottom-[9px] h-0.5 rounded-full bg-accent" aria-hidden />}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <HealthDot />
          <button
            type="button"
            className="inline-flex size-9 items-center justify-center rounded-md text-white hover:bg-white/10 md:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? <X className="size-5" aria-hidden /> : <Menu className="size-5" aria-hidden />}
          </button>
        </div>
      </div>

      {open && (
        <nav id="mobile-nav" aria-label="Main" className="border-t border-white/10 bg-primary-dark md:hidden">
          <ul className="mx-auto flex max-w-7xl flex-col px-2 py-2">
            {NAV.map((item) => {
              const current = isCurrent(pathname, item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={current ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-2 rounded-md px-3 py-2.5 text-sm font-medium",
                      current ? "bg-white/12 text-white" : "text-white/85 hover:bg-white/8",
                    )}
                  >
                    <item.icon className="size-4" aria-hidden />
                    {item.label}
                    {current && <span className="ml-auto size-1.5 rounded-full bg-accent" aria-hidden />}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </header>
  );
}
