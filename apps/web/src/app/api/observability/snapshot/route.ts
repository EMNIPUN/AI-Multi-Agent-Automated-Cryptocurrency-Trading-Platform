import { NextResponse } from "next/server";

import { localAgentFixture } from "@/lib/fixtures/agentSnapshot";
import {
  apiInternalBase,
  bearerFromRequest,
  proxyJsonToFastApi,
} from "@/lib/security/authenticated-proxy";
import { operatorLocalBrowserProxyEnabled } from "@/lib/security/operator-proxy-gate";

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
 * source=worker → JWT-forwarded owner-bound snapshot, or optional operator break-glass.
 */
export async function GET(request: Request) {
  const source = new URL(request.url).searchParams.get("source") ?? "worker";

  if (source !== "sample") {
    const token = bearerFromRequest(request);
    const breakGlass = operatorLocalBrowserProxyEnabled();
    if (!token && !breakGlass) {
      return NextResponse.json(
        unavailable(
          "Worker telemetry requires Authorization Bearer token (owner-bound) or explicit operator-local break-glass.",
        ),
        { headers: { "Cache-Control": "no-store" } },
      );
    }
    if (token) {
      const authed = await proxyJsonToFastApi(
        request,
        "/api/v1/observability/worker-snapshot",
        { allowOperatorBreakGlass: false },
      );
      // Local single-operator: JWT + PRIVATE_DATA_READS off returns 403
      // (ownership_schema_required). Fall back to loopback diagnostic when
      // break-glass is explicitly enabled — never invent telemetry.
      if (authed.status === 403 && breakGlass) {
        const detail = await authed
          .clone()
          .json()
          .then((body: { detail?: string }) => String(body?.detail || ""))
          .catch(() => "");
        if (
          detail === "ownership_schema_required" ||
          detail === "exchange_binding_missing" ||
          detail === "forbidden"
        ) {
          try {
            const res = await fetch(`${apiInternalBase()}/api/v1/observability/worker-snapshot`, {
              headers: { Accept: "application/json" },
              cache: "no-store",
              redirect: "error",
            });
            const payload = await res.json().catch(() => ({ detail: "invalid_json" }));
            return NextResponse.json(payload, {
              status: res.status,
              headers: { "Cache-Control": "no-store" },
            });
          } catch {
            return NextResponse.json(
              unavailable("Worker telemetry API unreachable for operator-local fallback."),
              { headers: { "Cache-Control": "no-store" } },
            );
          }
        }
      }
      return authed;
    }
    return proxyJsonToFastApi(request, "/api/v1/observability/worker-snapshot", {
      allowOperatorBreakGlass: true,
    });
  }

  const base = apiInternalBase();
  try {
    const res = await fetch(`${base}/api/v1/observability/snapshot`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (res.ok) {
      return NextResponse.json(await res.json(), {
        headers: { "Cache-Control": "no-store" },
      });
    }
  } catch {
    // fall through
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
