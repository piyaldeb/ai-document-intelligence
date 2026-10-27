import type { Metadata } from "next";
import { Suspense } from "react";
import { ReconcileView } from "@/components/reconcile/reconcile-view";
import { LoadingState } from "@/components/ui";

export const metadata: Metadata = { title: "Cross-verify" };

export default function ReconcilePage() {
  return (
    <Suspense fallback={<LoadingState label="Loading…" />}>
      <ReconcileView />
    </Suspense>
  );
}
