"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";

type Unread = { enabled?: boolean; unread?: number; detail?: string };

export function NewsAlertStrip() {
  const [state, setState] = useState<"loading" | "disabled" | "error" | "ready">("loading");
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/news/alerts/unread-count", { cache: "no-store" });
        const body = (await res.json()) as Unread;
        if (cancelled) return;
        if (res.status === 503 || body.enabled === false) {
          setState("disabled");
          return;
        }
        if (!res.ok) {
          setState("error");
          return;
        }
        setUnread(Number(body.unread || 0));
        setState("ready");
      } catch {
        if (!cancelled) setState("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <div>
        <p className="text-sm font-medium">News alerts</p>
        <p className="text-xs text-white/50">
          {state === "loading" && "Checking alert storage…"}
          {state === "disabled" && "Alert engine is off. No demo alerts are shown."}
          {state === "error" && "Alert center unavailable. News storage did not respond."}
          {state === "ready" && `${unread} unread in-app alert${unread === 1 ? "" : "s"}.`}
        </p>
      </div>
      <div className="flex items-center gap-2">
        {state === "ready" && unread > 0 ? <Badge variant="danger">{unread} unread</Badge> : null}
        <Link href="/news" className="text-sm text-white/80 underline-offset-4 hover:underline">
          Open news
        </Link>
      </div>
    </div>
  );
}
