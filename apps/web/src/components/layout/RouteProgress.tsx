"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

/**
 * Thin top progress bar on route changes.
 * Stays near-complete until the pathname actually updates (covers slow
 * first-compile navigations in `next dev`).
 */
export function RouteProgress() {
  const pathname = usePathname();
  const [active, setActive] = useState(false);
  const [width, setWidth] = useState(0);
  const pendingFrom = useRef<string | null>(null);
  const tick = useRef<ReturnType<typeof setInterval> | null>(null);
  const finishTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipSoft = useRef(false);

  const clearTick = useCallback(() => {
    if (tick.current) {
      clearInterval(tick.current);
      tick.current = null;
    }
  }, []);

  const finish = useCallback(() => {
    clearTick();
    setWidth(100);
    if (finishTimer.current) clearTimeout(finishTimer.current);
    finishTimer.current = setTimeout(() => {
      setActive(false);
      setWidth(0);
      pendingFrom.current = null;
    }, 180);
  }, [clearTick]);

  const start = useCallback(
    (fromPath: string) => {
      if (pendingFrom.current === fromPath && active) return;
      pendingFrom.current = fromPath;
      skipSoft.current = true;
      if (finishTimer.current) clearTimeout(finishTimer.current);
      clearTick();
      setActive(true);
      setWidth(12);
      tick.current = setInterval(() => {
        setWidth((w) => {
          if (w >= 88) return w;
          if (w < 40) return w + 10;
          if (w < 70) return w + 4;
          return w + 1.2;
        });
      }, 220);
    },
    [active, clearTick],
  );

  useEffect(() => {
    if (pendingFrom.current && pendingFrom.current !== pathname) {
      finish();
      return;
    }
    if (skipSoft.current) {
      skipSoft.current = false;
      return;
    }
    if (pendingFrom.current) return;

    setActive(true);
    setWidth(55);
    const t1 = setTimeout(() => setWidth(100), 80);
    const t2 = setTimeout(() => {
      setActive(false);
      setWidth(0);
    }, 260);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [pathname, finish]);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (event.button !== 0) return;
      if (event.metaKey || event.altKey || event.ctrlKey || event.shiftKey) return;
      const target = event.target as Element | null;
      const anchor = target?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!anchor) return;
      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("#") || href.startsWith("mailto:")) return;
      try {
        const url = new URL(href, window.location.origin);
        if (url.origin !== window.location.origin) return;
        if (url.pathname === pathname && url.search === window.location.search) return;
        // Capture-phase: fire even when sidebar preventDefault's the click
        start(pathname);
      } catch {
        /* ignore */
      }
    };

    document.addEventListener("click", onClick, true);
    return () => {
      document.removeEventListener("click", onClick, true);
      clearTick();
      if (finishTimer.current) clearTimeout(finishTimer.current);
    };
  }, [pathname, start, clearTick]);

  if (!active && width === 0) return null;

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-x-0 top-0 z-[100] h-[2px] overflow-hidden"
    >
      <div
        className={cn(
          "h-full bg-gradient-to-r from-brand via-chart-1 to-primary/40 shadow-[0_0_12px_hsl(var(--brand)/0.45)] transition-[width] duration-200 ease-out",
          !active && "opacity-0",
        )}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}
