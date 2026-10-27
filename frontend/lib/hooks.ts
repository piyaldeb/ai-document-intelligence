"use client";

import { useCallback, useEffect, useEffectEvent, useState, useSyncExternalStore } from "react";
import { ApiError, api, isAbortError } from "./api";

interface ApiState<T> {
  key: string | null;
  data: T | undefined;
  error: ApiError | Error | null;
}

export interface UseApiResult<T> {
  data: T | undefined;
  error: ApiError | Error | null;
  /** True while the current URL has not resolved yet (previous data stays visible). */
  loading: boolean;
  reload: () => void;
  mutate: (update: T | ((prev: T | undefined) => T | undefined)) => void;
}

/**
 * GET a JSON resource. Stale-while-revalidate: when `url` changes or `reload()` is called the
 * previous data stays visible while `loading` is true, so filters and polling never flash.
 * Pass `null` to skip fetching.
 */
export function useApi<T>(url: string | null): UseApiResult<T> {
  const [nonce, setNonce] = useState(0);
  const key = url ? `${nonce}|${url}` : null;
  const [state, setState] = useState<ApiState<T>>({ key: null, data: undefined, error: null });

  useEffect(() => {
    if (!url || !key) return;
    const ctrl = new AbortController();
    api<T>(url, { signal: ctrl.signal }).then(
      (data) => setState({ key, data, error: null }),
      (error: unknown) => {
        if (ctrl.signal.aborted || isAbortError(error)) return;
        setState((prev) => ({
          key,
          data: prev.data,
          error: error instanceof Error ? error : new Error(String(error)),
        }));
      },
    );
    return () => ctrl.abort();
  }, [url, key]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const mutate = useCallback((update: T | ((prev: T | undefined) => T | undefined)) => {
    setState((prev) => ({
      ...prev,
      data: typeof update === "function" ? (update as (p: T | undefined) => T | undefined)(prev.data) : update,
    }));
  }, []);

  const settled = key !== null && state.key === key;
  return {
    data: state.data,
    error: settled ? state.error : null,
    loading: key !== null && !settled,
    reload,
    mutate,
  };
}

/**
 * Run `callback` every `ms` while `ms` is not null. Pauses while the tab is hidden, fires
 * immediately when it becomes visible again, and never overlaps two runs.
 */
export function usePolling(callback: () => void | Promise<void>, ms: number | null): void {
  const onTick = useEffectEvent(callback);
  useEffect(() => {
    if (ms === null) return;
    let inFlight = false;
    const tick = async () => {
      if (inFlight || document.visibilityState === "hidden") return;
      inFlight = true;
      try {
        await onTick();
      } catch {
        /* the next tick retries */
      } finally {
        inFlight = false;
      }
    };
    const timer = window.setInterval(tick, ms);
    const onVisible = () => {
      if (document.visibilityState === "visible") void tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [ms]);
}

const storageListeners = new Set<() => void>();

function subscribeStorage(cb: () => void): () => void {
  storageListeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    storageListeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
}

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // storage unavailable (privacy mode)
  }
}

/** A value persisted in localStorage (e.g. the reviewer's name for the audit trail). */
export function useLocalStorage(key: string, initial = ""): [string, (v: string) => void] {
  const value = useSyncExternalStore(
    subscribeStorage,
    () => readStorage(key) ?? initial,
    () => initial,
  );
  const update = useCallback(
    (v: string) => {
      try {
        window.localStorage.setItem(key, v);
      } catch {
        /* storage unavailable */
      }
      storageListeners.forEach((l) => l());
    },
    [key],
  );
  return [value, update];
}

/** Re-render periodically so relative timestamps ("2 min ago") stay fresh. */
export function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(t);
  }, [intervalMs]);
  return now;
}
