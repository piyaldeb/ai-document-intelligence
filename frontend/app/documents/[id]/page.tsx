import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { DocumentView } from "@/components/document/document-view";
import { LoadingState } from "@/components/ui";
import { isUuid } from "@/lib/ids";

export const metadata: Metadata = { title: "Document" };

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) notFound();
  return (
    <Suspense fallback={<LoadingState label="Loading document…" />}>
      <DocumentView key={id} id={id} />
    </Suspense>
  );
}
