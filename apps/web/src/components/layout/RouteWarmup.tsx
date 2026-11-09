"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { NAV_GROUPS } from "@/lib/nav";

/** Pages + APIs to compile ahead of first click (dev on-demand compile). */
const WARM_APIS = [
  "/api/paper/status",
  "/api/paper/sessions",
  "/api/backtests/status",
  "/api/backtests/runs?limit=1",
  "/api/exchange/wallet",
  "/api/signals/status",
  "/api/orchestrator/status",
  "/api/llm/status",
  "/api/news/status",
] as const;

function idle(cb: () => void, timeout = 1800) {
  if (typeof window === "undefined") return () => undefined;
  const w = window as Window &
    typeof globalThis & {
      requestIdleCallback?: (cb: IdleRequestCallback, opts?: IdleRequestOptions) => number;
      cancelIdleCallback?: (id: number) => void;
    };
  if (typeof w.requestIdleCallback === "function") {
    const id = w.requestIdleCallback(cb, { timeout });
    return () => w.cancelIdleCallback?.(id);
  }
  const id = globalThis.setTimeout(cb, 400);
  return () => globalThis.clearTimeout(id);
}

/**
 * Prefetch workspace routes and quietly hit common APIs so the first
 * navigation / data fetch does not wait on Next.js compiling cold modules.
 */
export function RouteWarmup() {
  const router = useRouter();

  useEffect(() => {
    const hrefs = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.href));
    const unique = Array.from(
      new Set([...hrefs, "/notifications", "/strategy", "/system", "/orchestrator"]),
    );

    let cancelled = false;
    let apiIndex = 0;

    const warmApis = () => {
      if (cancelled || apiIndex >= WARM_APIS.length) return;
      const path = WARM_APIS[apiIndex++];
      void fetch(path, {
        method: "GET",
        cache: "no-store",
        credentials: "same-origin",
      }).catch(() => undefined);
      // Stagger so we don't spike the compiler
      window.setTimeout(warmApis, 350);
    };

    const cancelIdle = idle(() => {
      if (cancelled) return;
      for (const href of unique) {
        try {
          router.prefetch(href);
        } catch {
          /* ignore */
        }
      }
      warmApis();
    });

    return () => {
      cancelled = true;
      cancelIdle();
    };
  }, [router]);

  return null;
}
