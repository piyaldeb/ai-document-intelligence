import type { Metadata } from "next";
import { Suspense } from "react";
import { InvoiceListView } from "@/components/invoices/invoice-list-view";
import { LoadingState } from "@/components/ui";

export const metadata: Metadata = { title: "Invoices" };

export default function InvoicesPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading invoices…" />}>
      <InvoiceListView />
    </Suspense>
  );
}
