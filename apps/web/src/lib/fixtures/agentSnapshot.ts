import type { AgentSnapshot, PaperWorkspaceSnapshot } from "@/lib/observability/types";

/** Bundled SAMPLE fixture — used when API is unreachable. Always labeled. */
export function localAgentFixture(): AgentSnapshot {
  const now = new Date();
  const iso = (mins: number) =>
    new Date(now.getTime() - mins * 60_000).toISOString();
  const step = 15 * 60;
  const end = Math.floor(now.getTime() / 1000);
  const aligned = end - (end % step) - step;
  const candles = Array.from({ length: 40 }, (_, i) => {
    const t = aligned - (39 - i) * step;
    const open = 67000 + i * 12;
    const close = open + ((i % 3) - 1) * 40;
    return {
      time: t,
      open,
      high: Math.max(open, close) + 30,
      low: Math.min(open, close) - 30,
      close,
      volume: 100 + i,
    };
  });
  const corr = "corr-local-sample";
  return {
    schema_version: "1.0.0",
    data_mode: "fixture",
    sample_label: "SAMPLE",
    generated_at: now.toISOString(),
    agent_status: "OFFLINE",
    heartbeat_at: iso(45),
    heartbeat_stale: true,
    stale_after_seconds: 30,
    symbol: "BTCUSDT",
    interval: "15",
    execution_mode: "DRY_RUN",
    money_view: "paper",
    last_confirmed_candle_at: new Date(candles[candles.length - 1].time * 1000).toISOString(),
    ema_fast: 67110.2,
    ema_slow: 66840.8,
    rsi: 54.3,
    signal_action: "HOLD",
    signal_reason: "local_fixture_mid_range",
    risk_verdict: "BLOCKED",
    risk_reasons: ["fixture_mode", "worker_offline"],
    current_pipeline_step: "blocked",
    pipeline_blocked: true,
    pipeline_block_reason: "Worker offline — SAMPLE fixture only (not live trading)",
    candles,
    markers: [
      {
        time: candles[candles.length - 4].time,
        action: "HOLD",
        price: candles[candles.length - 4].close,
        label: "SAMPLE HOLD",
        sample: true,
      },
    ],
    orders: [
      {
        client_order_id: "sample-intent-local",
        state: "DRY_RUN",
        side: "Buy",
        qty: "0.001",
        filled_qty: "0",
        correlation_id: corr,
        updated_at: iso(10),
        sample: true,
      },
    ],
    events: [
      {
        schema_version: "1.0.0",
        event_id: "evt-local-0001",
        event_type: "agent.heartbeat",
        occurred_at: iso(45),
        correlation_id: corr,
        env_scope: "fixture",
        execution_mode: "DRY_RUN",
        pipeline_step: "market_data",
        message: "Stale heartbeat (sample)",
        payload: { status: "OFFLINE" },
        symbol: "BTCUSDT",
        interval: "15",
      },
      {
        schema_version: "1.0.0",
        event_id: "evt-local-0002",
        event_type: "signal.generated",
        occurred_at: iso(12),
        correlation_id: corr,
        env_scope: "fixture",
        execution_mode: "DRY_RUN",
        pipeline_step: "signal",
        message: "SAMPLE signal HOLD",
        payload: { action: "HOLD" },
        symbol: "BTCUSDT",
        interval: "15",
      },
      {
        schema_version: "1.0.0",
        event_id: "evt-local-0003",
        event_type: "risk.blocked",
        occurred_at: iso(11),
        correlation_id: corr,
        env_scope: "fixture",
        execution_mode: "DRY_RUN",
        pipeline_step: "blocked",
        message: "Risk blocked (sample)",
        payload: { reasons: ["worker_offline"] },
        symbol: "BTCUSDT",
        interval: "15",
      },
    ],
    cursor: "evt-local-0003",
    notes: [
      "Bundled SAMPLE fixture — API unreachable or fixture mode.",
      "No live Bybit activity is implied.",
    ],
  };
}

export function localPaperFixture(): PaperWorkspaceSnapshot {
  return {
    schema_version: "1.0.0",
    data_mode: "fixture",
    sample_label: "SAMPLE",
    generated_at: new Date().toISOString(),
    virtual_equity: 10000,
    cash: 9420.55,
    unrealized_pnl: 42.1,
    realized_pnl: -18.25,
    positions: [
      {
        symbol: "BTCUSDT",
        side: "Buy",
        qty: "0.01",
        entry: 66800,
        mark: 67220,
        sl: 66100,
        tp: 68500,
        sample: true,
      },
    ],
    simulated_orders: [
      {
        id: "paper-ord-local",
        symbol: "BTCUSDT",
        side: "Buy",
        qty: "0.01",
        state: "FILLED",
        sample: true,
      },
    ],
    history: [
      {
        ts: new Date(Date.now() - 3_600_000).toISOString(),
        action: "BUY",
        symbol: "BTCUSDT",
        pnl: -18.25,
        sample: true,
      },
    ],
    submit_controls_enabled: false,
    broker_implemented: false,
    notes: [
      "Paper workspace SAMPLE only — submit controls disabled.",
      "No paper broker persistence yet.",
    ],
  };
}
