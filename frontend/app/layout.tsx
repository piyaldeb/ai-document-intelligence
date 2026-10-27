import type { Metadata, Viewport } from "next";
import { Fira_Sans, Poppins } from "next/font/google";
import { SiteHeader } from "@/components/site-header";
import { ToastProvider } from "@/components/toast";
import "./globals.css";

const poppins = Poppins({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-poppins",
  display: "swap",
});

const firaSans = Fira_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-fira-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "DocIntel", template: "%s · DocIntel" },
  description: "Document intelligence: extract, validate, correct, search and cross-verify invoices.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: "#1a365d",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${poppins.variable} ${firaSans.variable}`}>
      {/* Browser extensions (e.g. Grammarly) inject attributes on <body>; don't flag those as hydration errors. */}
      <body className="min-h-dvh" suppressHydrationWarning>
        <a
          href="#main"
          className="sr-only z-50 rounded-md bg-accent px-3 py-2 font-semibold text-ink focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
        >
          Skip to content
        </a>
        <ToastProvider>
          <SiteHeader />
          <main id="main" className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
            {children}
          </main>
          <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-muted sm:px-6">
            DocIntel · AI document intelligence for invoices, receipts and statements
          </footer>
        </ToastProvider>
      </body>
    </html>
  );
}
