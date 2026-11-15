"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiError, ApiResult } from "@/lib/api/client";

export type PolledResource<T> = {
  data: T | null;
  error: ApiError | null;
  /** True until the first response (success or failure) lands. */
  loading: boolean;
  /** True while a refresh is in flight after the first load. */
  refreshing: boolean;
  /** Timestamp (ms) of the last successful response. */
  updatedAt: number | null;
  /** Manually refresh. Resolves when the request settles. */
  refresh: () => Promise<void>;
};

type Options = {
  /** Poll interval in ms. 0 disables polling (fetch once). */
  intervalMs?: number;
  /** Skip the request entirely (e.g. until auth is ready). */
  enabled?: boolean;
  /** Pause polling while the tab is hidden (default true). */
  pauseWhenHidden?: boolean;
};

/**
 * Single-subscription polling for one API resource.
 *
 * - Aborts in-flight requests on unmount / refetch (no duplicate calls under
 *   React StrictMode double-effects).
 * - Pauses while the document is hidden and refreshes on return.
 * - Keeps the last good data while a refresh fails, exposing the error alongside.
 */
export function usePolledResource<T>(
  fetcher: (init: RequestInit) => Promise<ApiResult<T>>,
  { intervalMs = 0, enabled = true, pauseWhenHidden = true }: Options = {},
): PolledResource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);
  const mountedRef = useRef(false);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(async () => {
    if (!enabled) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const seq = ++seqRef.current;
    setRefreshing(true);
    const result = await fetcherRef.current({ signal: controller.signal });
    if (!mountedRef.current || seq !== seqRef.current) return;
    if (result.ok) {
      setData(result.data);
      setError(null);
      setUpdatedAt(result.at);
    } else if (result.code !== "aborted") {
      setError(result);
    }
    setLoading(false);
    setRefreshing(false);
  }, [enabled]);

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled) {
      setLoading(false);
      return () => {
        mountedRef.current = false;
      };
    }
    void run();
    let timer: number | null = null;
    const schedule = () => {
      if (intervalMs > 0 && timer === null) {
        timer = window.setInterval(() => {
          if (pauseWhenHidden && document.hidden) return;
          void run();
        }, intervalMs);
      }
    };
    const onVisible = () => {
      if (!document.hidden) void run();
    };
    schedule();
    if (pauseWhenHidden) document.addEventListener("visibilitychange", onVisible);
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
      if (timer !== null) window.clearInterval(timer);
      if (pauseWhenHidden) document.removeEventListener("visibilitychange", onVisible);
    };
  }, [run, intervalMs, enabled, pauseWhenHidden]);

  return { data, error, loading, refreshing, updatedAt, refresh: run };
}

/** A ticking "now" for relative timestamps without re-rendering every frame. */
export function useNow(everyMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), everyMs);
    return () => window.clearInterval(id);
  }, [everyMs]);
  return now;
}
