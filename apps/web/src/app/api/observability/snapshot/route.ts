import { NextResponse } from "next/server";

import { localAgentFixture } from "@/lib/fixtures/agentSnapshot";

function unavailable(note: string) {
  return {
    schema_version: "1.0.0",
    data_mode: "unavailable",
    sample_label: null,
    generated_at: new Date().toISOString(),
    agent_status: "UNKNOWN",
    heartbeat_at: null,
    heartbeat_stale: true,
    stale_after_seconds: 120,
    symbol: "—",
    interval: "—",
    execution_mode: "DRY_RUN",
    money_view: "real_readonly",
    last_confirmed_candle_at: null,
    ema_fast: null,
    ema_slow: null,
    rsi: null,
    signal_action: null,
    signal_reason: null,
    risk_verdict: "UNKNOWN",
    risk_reasons: [],
    current_pipeline_step: "unknown",
    pipeline_blocked: false,
    pipeline_block_reason: null,
    candles: [],
    markers: [],
    orders: [],
    events: [],
    cursor: null,
    notes: [note, "SAMPLE fixtures are not mixed into this response."],
  };
}

/**
 * Same-origin proxy.
 * source=sample → labeled fixtures.
 * source=worker (default) → loopback worker ledger only, never fixtures.
 * JWTs are not placed in query strings.
 */
export async function GET(request: Request) {
  const source = new URL(request.url).searchParams.get("source") ?? "worker";
  const base = process.env.API_INTERNAL_BASE_URL?.replace(/\/$/, "");

  if (source !== "sample") {
    if (!base) {
      return NextResponse.json(unavailable("API base URL is not configured."));
    }
    try {
      const res = await fetch(`${base}/api/v1/observability/worker-snapshot`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!res.ok) {
        return NextResponse.json(
          unavailable("Worker telemetry is not authorized or not reachable."),
        );
      }
      return NextResponse.json(await res.json());
    } catch {
      return NextResponse.json(unavailable("Worker telemetry request failed."));
    }
  }

  if (base) {
    try {
      const res = await fetch(`${base}/api/v1/observability/snapshot`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (res.ok) {
        return NextResponse.json(await res.json());
      }
    } catch {
      // fall through to local fixture
    }
  }
  const fixture = localAgentFixture();
  return NextResponse.json({
    ...fixture,
    notes: [
      ...fixture.notes,
      "Served by Next.js same-origin proxy (API unavailable) — SAMPLE only.",
    ],
  });
}
