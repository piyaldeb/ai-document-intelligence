import { Fragment } from "react";

/**
 * Render a search snippet in which the backend marks matched words as <<word>>.
 * Everything is rendered as React text nodes (auto-escaped); only the marked spans become
 * <mark> elements. No dangerouslySetInnerHTML anywhere.
 */
export function Highlighted({ text }: { text: string }) {
  // With a capturing group, split() alternates [plain, match, plain, match, ...].
  const parts = text.split(/<<([\s\S]*?)>>/g);
  return (
    <>
      {parts.map((part, i) => (i % 2 === 1 ? <mark key={i}>{part}</mark> : <Fragment key={i}>{part}</Fragment>))}
    </>
  );
}
