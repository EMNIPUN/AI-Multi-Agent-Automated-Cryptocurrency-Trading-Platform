"use client";

import { useEffect, useState } from "react";

import { LogoLoader } from "@/components/brand/LogoLoader";
import { CandleChart } from "@/components/CandleChart";
import { EventTimeline } from "@/components/EventTimeline";
import { OrderLifecycle } from "@/components/OrderLifecycle";
import { PipelineViz } from "@/components/PipelineViz";
import { SampleBanner } from "@/components/SampleBanner";
import { StatusBadge } from "@/components/StatusBadge";
import { WalletBalancePanel } from "@/components/WalletBalancePanel";
import { localAgentFixture } from "@/lib/fixtures/agentSnapshot";
import type { AgentSnapshot } from "@/lib/observability/types";

type LoadState = "loading" | "ready" | "unavailable";

export function AgentCommandCenter() {
  const [state, setState] = useState<LoadState>("loading");
  const [snap, setSnap] = useState<AgentSnapshot | null>(null);
  const [source, setSource] = useState<"api" | "local-fixture">("local-fixture");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/observability/snapshot", { cache: "no-store" });
        if (!res.ok) throw new Error("snapshot_failed");
        const data = (await res.json()) as AgentSnapshot;
        if (cancelled) return;
        setSnap(data);
        setSource("api");
        setState("ready");
      } catch {
        if (cancelled) return;
        setSnap(localAgentFixture());
        setSource("local-fixture");
        setState("unavailable");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state === "loading" || !snap) {
    return <LogoLoader fullScreen label="Loading agent snapshot…" />;
  }

  const sample = snap.data_mode !== "live";
  const moneyLabel =
    snap.money_view === "paper" ? "Paper / virtual money view" : "Real-money read-only view";

  return (
    <div>
      <SampleBanner dataMode={snap.data_mode} notes={snap.notes} />
      {state === "unavailable" ? (
        <p className="badge warn" style={{ marginBottom: "1rem" }}>
          Disconnected from API — showing bundled SAMPLE fixture
        </p>
      ) : null}

      <div className="meta-row">
        <div className="metric">
          <span className="label">Agent status</span>
          <div className="value">
            <StatusBadge status={snap.agent_status} />
          </div>
        </div>
        <div className="metric">
          <span className="label">Heartbeat</span>
          <div className="value">
            {snap.heartbeat_at
              ? new Date(snap.heartbeat_at).toISOString()
              : "unavailable"}
          </div>
          {snap.heartbeat_stale ? (
            <span className="badge warn">STALE</span>
          ) : (
            <span className="badge ok">FRESH</span>
          )}
        </div>
        <div className="metric">
          <span className="label">Symbol / interval</span>
          <div className="value">
            {snap.symbol} · {snap.interval}m
          </div>
        </div>
        <div className="metric">
          <span className="label">Execution mode</span>
          <div className="value">{snap.execution_mode}</div>
        </div>
        <div className="metric">
          <span className="label">Money view</span>
          <div className="value">{moneyLabel}</div>
        </div>
        <div className="metric">
          <span className="label">Last confirmed candle</span>
          <div className="value">
            {snap.last_confirmed_candle_at
              ? new Date(snap.last_confirmed_candle_at).toISOString()
              : "unavailable"}
          </div>
        </div>
      </div>

      <PipelineViz
        current={snap.current_pipeline_step}
        blocked={snap.pipeline_blocked}
        blockReason={snap.pipeline_block_reason}
      />

      <div style={{ marginTop: "1rem" }}>
        <WalletBalancePanel />
      </div>

      <div className="grid-main" style={{ marginTop: "1rem" }}>
        <section className="panel">
          <h2>Confirmed candles {sample ? <span className="badge sample">SAMPLE</span> : null}</h2>
          <CandleChart
            candles={snap.candles}
            markers={snap.markers}
            sample={sample}
          />
          <div className="meta-row" style={{ marginTop: "0.75rem", marginBottom: 0 }}>
            <div className="metric">
              <span className="label">EMA fast</span>
              <div className="value">
                {snap.ema_fast != null ? snap.ema_fast.toFixed(2) : "unavailable"}
              </div>
            </div>
            <div className="metric">
              <span className="label">EMA slow</span>
              <div className="value">
                {snap.ema_slow != null ? snap.ema_slow.toFixed(2) : "unavailable"}
              </div>
            </div>
            <div className="metric">
              <span className="label">RSI</span>
              <div className="value">
                {snap.rsi != null ? snap.rsi.toFixed(1) : "unavailable"}
              </div>
            </div>
            <div className="metric">
              <span className="label">Signal</span>
              <div className="value">{snap.signal_action ?? "unavailable"}</div>
              <span className="muted">{snap.signal_reason ?? ""}</span>
            </div>
            <div className="metric">
              <span className="label">Risk verdict</span>
              <div className="value">{snap.risk_verdict}</div>
              <span className="muted">{snap.risk_reasons.join("; ") || "—"}</span>
            </div>
          </div>
        </section>

        <div style={{ display: "grid", gap: "1rem" }}>
          <OrderLifecycle orders={snap.orders} />
          <EventTimeline events={snap.events} sample={sample} />
          <section className="panel">
            <h3>Feed source</h3>
            <p className="muted" style={{ margin: 0 }}>
              {source} · cursor={snap.cursor ?? "—"} · schema {snap.schema_version}
            </p>
            <p className="muted">
              Live SSE disabled until ownership migration is applied and private
              reads are explicitly enabled. Frontend state is never execution
              authority.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
