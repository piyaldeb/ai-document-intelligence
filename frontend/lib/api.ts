/**
 * Browser-side API client. Every call goes to the same-origin proxy (/api/...), which adds
 * the backend API key on the server. Errors are normalised from FastAPI's `{detail}` shape.
 */
import type { UploadResponse } from "./types";

type ValidationEntry = { loc?: (string | number)[]; msg?: string; type?: string };

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  /** Field-level messages from a 422 validation array, keyed by the last `loc` element. */
  readonly fieldErrors: Record<string, string>;

  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? formatDetail(detail, status));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.fieldErrors = extractFieldErrors(detail);
  }
}

function isValidationArray(detail: unknown): detail is ValidationEntry[] {
  return Array.isArray(detail) && detail.every((d) => typeof d === "object" && d !== null);
}

function locLabel(loc: (string | number)[] | undefined): string {
  if (!loc?.length) return "";
  const parts = loc.filter((p) => p !== "body" && p !== "query" && p !== "path");
  return parts.join(".");
}

export function formatDetail(detail: unknown, status?: number): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (isValidationArray(detail) && detail.length) {
    return detail
      .map((d) => {
        const where = locLabel(d.loc);
        return where ? `${where}: ${d.msg ?? "invalid value"}` : (d.msg ?? "Invalid value");
      })
      .join("; ");
  }
  if (status === 401) return "The API rejected the web server's credentials. Check the proxy's API key configuration.";
  if (status === 429) return "Too many requests. Please wait a moment and try again.";
  if (status && status >= 500) return `The server returned an error (${status}).`;
  return status ? `Request failed (${status}).` : "Request failed.";
}

function extractFieldErrors(detail: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!isValidationArray(detail)) return out;
  for (const d of detail) {
    const parts = (d.loc ?? []).filter((p) => p !== "body");
    if (!parts.length) continue;
    const key = parts.map(String).join(".");
    out[key] = d.msg ?? "Invalid value";
    // Also index by the top-level field so the form can highlight it.
    out[String(parts[0])] ??= d.msg ?? "Invalid value";
  }
  return out;
}

async function parseError(res: Response): Promise<ApiError> {
  let detail: unknown = undefined;
  try {
    const ct = res.headers.get("content-type") ?? "";
    if (ct.includes("application/json")) {
      const body = (await res.json()) as { detail?: unknown };
      detail = body?.detail ?? body;
    } else {
      const text = await res.text();
      detail = text.slice(0, 300) || undefined;
    }
  } catch {
    /* body unreadable: fall back to the status message */
  }
  return new ApiError(res.status, detail);
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = opts;
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(path, { method, headers, body: payload, signal, cache: "no-store" });
  } catch (err) {
    if (signal?.aborted) throw err;
    throw new ApiError(0, undefined, "Network error: could not reach the DocIntel server.");
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  if (!ct.includes("application/json")) return (await res.text()) as unknown as T;
  return (await res.json()) as T;
}

export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

/** Build `?a=1&b=2`, skipping empty values. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export interface UploadHandle {
  promise: Promise<UploadResponse>;
  abort: () => void;
}

/**
 * Multipart upload with progress (fetch has no upload progress events, XHR does).
 * Field name is `files` (repeated), as expected by POST /api/documents.
 */
export function uploadFiles(files: File[], onProgress: (loaded: number, total: number) => void): UploadHandle {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<UploadResponse>((resolve, reject) => {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    xhr.open("POST", "/api/documents");
    xhr.setRequestHeader("Accept", "application/json");
    xhr.responseType = "text";
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded, e.total);
    };
    xhr.onload = () => {
      let body: unknown = undefined;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
      } catch {
        body = xhr.responseText;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as UploadResponse);
      } else {
        const detail = typeof body === "object" && body !== null && "detail" in body ? (body as { detail: unknown }).detail : body;
        reject(new ApiError(xhr.status, detail));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, undefined, "Network error during upload."));
    xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}
