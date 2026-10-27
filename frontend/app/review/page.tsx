import type { Metadata } from "next";
import { Suspense } from "react";
import { ReviewQueue } from "@/components/review/review-queue";
import { LoadingState } from "@/components/ui";

export const metadata: Metadata = { title: "Review queue" };

export default function ReviewPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading review queue…" />}>
      <ReviewQueue />
    </Suspense>
  );
}
