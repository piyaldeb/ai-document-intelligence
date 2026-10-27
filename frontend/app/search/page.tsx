import type { Metadata } from "next";
import { Suspense } from "react";
import { SearchView } from "@/components/search/search-view";
import { LoadingState } from "@/components/ui";

export const metadata: Metadata = { title: "Search" };

export default function SearchPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading search…" />}>
      <SearchView />
    </Suspense>
  );
}
