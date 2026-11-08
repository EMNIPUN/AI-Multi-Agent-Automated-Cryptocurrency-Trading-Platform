"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { authHeaders } from "@/lib/auth/browser-access-token";
import { localAgentFixture } from "@/lib/fixtures/agentSnapshot";
import type { AgentSnapshot } from "@/lib/observability/types";

import type { StudioViewMode } from "../types";

const POLL_MS = 4000;

export function useAgentSnapshot(viewMode: StudioViewMode) {
  const [snap, setSnap] = useState<AgentSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (viewMode === "replay") return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const source = viewMode === "sample" ? "sample" : "worker";
    try {
      const res = await fetch(`/api/observability/snapshot?source=${source}`, {
        cache: "no-store",
        signal: controller.signal,
        headers: source === "worker" ? await authHeaders() : undefined,
      });
      if (!res.ok) throw new Error(`snapshot_${res.status}`);
      const data = (await res.json()) as AgentSnapshot;
      if (source === "worker" && data.data_mode === "fixture") {
        // Never silently promote SAMPLE as LIVE.
        throw new Error("sample_leak_rejected");
      }
      setSnap(data);
      setError(null);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      if (viewMode === "sample") {
        setSnap(localAgentFixture());
        setError(null);
      } else {
        setError((err as Error).message || "disconnected");
        setSnap({
          ...localAgentFixture(),
          data_mode: "unavailable",
          sample_label: null,
          agent_status: "UNKNOWN",
          heartbeat_stale: true,
          events: [],
          orders: [],
          candles: [],
          markers: [],
          notes: [
            "Worker telemetry unavailable or unauthorized.",
            "LIVE never falls back to SAMPLE.",
            "Owner-bound reads require a Bearer access token after migrations + PRIVATE_DATA_READS.",
          ],
        });
      }
    } finally {
      setLoading(false);
    }
  }, [viewMode]);

  useEffect(() => {
    setLoading(true);
    void load();
    if (viewMode === "live") {
      const id = window.setInterval(() => {
        if (document.visibilityState === "hidden") return;
        void load();
      }, POLL_MS);
      return () => {
        window.clearInterval(id);
        abortRef.current?.abort();
      };
    }
    return () => abortRef.current?.abort();
  }, [load, viewMode]);

  return { snap, error, loading, reload: load };
}
