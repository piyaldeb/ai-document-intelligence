"use client";

import { useEffect } from "react";
import { Card, ErrorState } from "@/components/ui";

export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <Card>
      <ErrorState title="This page failed to render" error={error} onRetry={reset} />
    </Card>
  );
}
