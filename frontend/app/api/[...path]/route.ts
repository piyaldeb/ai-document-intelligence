/**
 * Server-side proxy: browser -> /api/<path> (same origin) -> ${BACKEND_URL}/api/<path>.
 *
 * - The backend API key is added here, from the server environment, at request time.
 *   It never reaches the browser bundle.
 * - Request bodies are streamed through (multipart uploads are never buffered in memory).
 * - Only an allow-list of response headers is passed back. In particular the backend's
 *   X-Frame-Options: DENY / CSP: sandbox are dropped, because the document preview embeds
 *   /api/documents/{id}/file in a same-origin iframe (next.config adds SAMEORIGIN + nosniff).
 */
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const FORWARD_REQUEST_HEADERS = ["content-type", "accept", "range", "if-range"] as const;
const FORWARD_RESPONSE_HEADERS = [
  "content-type",
  "content-disposition",
  "content-length",
  "cache-control",
  "content-range",
  "accept-ranges",
  "retry-after",
] as const;
const NULL_BODY_STATUSES = new Set([101, 204, 205, 304]);

type RouteContext = { params: Promise<{ path: string[] }> };

function backendBase(): string {
  return (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/+$/, "");
}

function jsonError(status: number, detail: string): Response {
  return Response.json({ detail }, { status, headers: { "cache-control": "no-store" } });
}

async function proxy(req: NextRequest, ctx: RouteContext): Promise<Response> {
  const { path } = await ctx.params;
  if (!path?.length || path.some((seg) => seg === "" || seg === "." || seg === "..")) {
    return jsonError(400, "Invalid API path");
  }
  const target = `${backendBase()}/api/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }
  // Ask for an uncompressed body so content-length stays truthful when streamed back.
  headers.set("accept-encoding", "identity");
  const apiKey = process.env.BACKEND_API_KEY;
  if (apiKey) headers.set("x-api-key", apiKey);
  const forwardedFor = req.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
  // The scheduled demo reset authenticates with its own bearer secret (checked by the API).
  const authorization = req.headers.get("authorization");
  if (authorization && path.join("/") === "admin/demo-reset") headers.set("authorization", authorization);

  const hasBody = req.method !== "GET" && req.method !== "HEAD" && req.body !== null;
  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers,
    body: hasBody ? req.body : undefined,
    // A streamed body cannot be replayed, so only body-less requests follow redirects.
    redirect: hasBody ? "manual" : "follow",
    cache: "no-store",
    signal: req.signal,
  };
  if (hasBody) init.duplex = "half"; // required by undici to stream a request body

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (err) {
    if (req.signal.aborted) return new Response(null, { status: 499 });
    console.error(`[api-proxy] ${req.method} /api/${path.join("/")} failed:`, err);
    return jsonError(502, "The DocIntel API is unreachable. Please try again in a moment.");
  }

  const out = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (!value) continue;
    // fetch() transparently decodes compressed bodies; the upstream length would then be wrong.
    if (name === "content-length" && upstream.headers.get("content-encoding")) continue;
    out.set(name, value);
  }
  if (!out.has("cache-control")) out.set("cache-control", "no-store");

  const body = NULL_BODY_STATUSES.has(upstream.status) || req.method === "HEAD" ? null : upstream.body;
  return new Response(body, { status: upstream.status, statusText: upstream.statusText, headers: out });
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
