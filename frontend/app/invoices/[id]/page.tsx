import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { InvoiceReview } from "@/components/review/invoice-review";
import { isUuid } from "@/lib/ids";

export const metadata: Metadata = { title: "Review invoice" };

export default async function InvoicePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) notFound();
  return <InvoiceReview key={id} id={id} />;
}
