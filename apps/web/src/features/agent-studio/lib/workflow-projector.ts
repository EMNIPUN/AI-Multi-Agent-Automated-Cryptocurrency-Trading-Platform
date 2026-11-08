import { dedupeEvents, sortEventsChronological } from "@/lib/observability/events";
import type { AgentSnapshot, ObservabilityEvent, PipelineStep } from "@/lib/observability/types";

import type {
  EventCategory,
  StrategyCondition,
  StrategyEvidence,
  StudioProjection,
  WorkflowNodeState,
  WorkflowStage,
} from "../types";

const STAGE_DEFS: Array<{
  id: string;
  step: PipelineStep | "execution";
  label: string;
  description: string;
  eventTypes: string[];
}> = [
  {
    id: "market",
    step: "market_data",
    label: "Market Data Collector",
    description: "Fetches exchange market data for the configured symbol.",
    eventTypes: ["agent.heartbeat"],
  },
  {
    id: "candle",
    step: "confirmed_candle",
    label: "Confirmed Candle Validator",
    description: "Accepts only finalized candles before analysis.",
    eventTypes: ["market.candle_confirmed"],
  },
  {
    id: "analysis",
    step: "strategy",
    label: "Technical Analysis Agent",
    description: "Computes EMA/RSI and related evidence.",
    eventTypes: ["analysis.completed"],
  },
  {
    id: "signal",
    step: "signal",
    label: "Signal Generator",
    description: "Produces BUY, SELL, or HOLD from strategy rules.",
    eventTypes: ["signal.generated"],
  },
  {
    id: "risk",
    step: "risk",
    label: "Risk Engine",
    description: "Approves, blocks, or halts proposed exposure.",
    eventTypes: ["risk.approved", "risk.blocked", "risk.halted", "agent.halted"],
  },
  {
    id: "intent",
    step: "intent",
    label: "Order Intent",
    description: "Local intent creation before any fill claim.",
    eventTypes: ["order.intent_created", "order.accepted"],
  },
  {
    id: "execution",
    step: "execution",
    label: "Execution / Simulation",
    description: "Exchange acknowledgment path. ACCEPTED is not FILLED.",
    eventTypes: ["order.accepted"],
  },
  {
    id: "reconcile",
    step: "reconciliation",
    label: "Reconciliation",
    description: "Fill evidence, cancels, and reconciliation required.",
    eventTypes: [
      "order.partially_filled",
      "order.filled",
      "order.canceled",
      "order.reconciliation_required",
    ],
  },
  {
    id: "position",
    step: "position",
    label: "Position / Outcome",
    description: "Confirmed position outcome when fill evidence exists.",
    eventTypes: ["order.filled"],
  },
];

export function categorizeEvent(eventType: string): EventCategory {
  if (eventType.startsWith("market.")) return "MARKET";
  if (eventType.startsWith("analysis.")) return "ANALYSIS";
  if (eventType.startsWith("signal.")) return "SIGNAL";
  if (eventType.startsWith("risk.")) return "RISK";
  if (eventType.startsWith("order.")) return "ORDER";
  if (eventType === "agent.error") return "ERROR";
  return "SYSTEM";
}

function latestMatching(
  events: ObservabilityEvent[],
  types: string[],
): ObservabilityEvent | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    if (types.includes(events[i].event_type)) return events[i];
  }
  return null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

export function extractStrategyEvidence(events: ObservabilityEvent[]): StrategyEvidence {
  const source =
    latestMatching(events, ["signal.generated"]) ??
    latestMatching(events, ["analysis.completed"]);
  const payload = source?.payload ?? {};
  const rawConditions = Array.isArray(payload.conditions) ? payload.conditions : [];
  const conditions: StrategyCondition[] = [];
  for (const item of rawConditions) {
    if (!item || typeof item !== "object") continue;
    const id = asString((item as { id?: unknown }).id);
    const result = asString((item as { result?: unknown }).result);
    if (!id || !result) continue;
    if (
      result === "PASS" ||
      result === "FAIL" ||
      result === "NOT_EVALUATED" ||
      result === "UNKNOWN"
    ) {
      conditions.push({ id, result });
    }
  }
  return {
    strategyId: asString(payload.strategy_id),
    strategyVersion: asString(payload.strategy_version),
    explanationCode: asString(payload.explanation_code),
    conditions,
    emaFastPeriod: asNumber(payload.ema_fast_period),
    emaSlowPeriod: asNumber(payload.ema_slow_period),
    rsiPeriod: asNumber(payload.rsi_period),
    rsiOverbought: asNumber(payload.rsi_overbought),
    rsiOversold: asNumber(payload.rsi_oversold),
    candleStartMs: asNumber(payload.candle_start_ms),
    candleCloseMs: asNumber(payload.candle_close_ms),
  };
}

export function chartTimeForEvent(
  event: ObservabilityEvent | null,
  candleTimes: Set<number>,
): number | null {
  if (!event) return null;
  const startMs = asNumber(event.payload.candle_start_ms);
  if (startMs != null) {
    const time = Math.floor(startMs / 1000);
    if (candleTimes.size === 0 || candleTimes.has(time)) return time;
    return null;
  }
  return null;
}

/** Detect chronological gaps larger than threshold (default 30m). */
export function detectReplayGaps(
  events: ObservabilityEvent[],
  thresholdMs = 30 * 60 * 1000,
): { hasGap: boolean; gapCount: number; largestGapMs: number } {
  let gapCount = 0;
  let largestGapMs = 0;
  for (let i = 1; i < events.length; i += 1) {
    const prev = Date.parse(events[i - 1].occurred_at);
    const next = Date.parse(events[i].occurred_at);
    if (!Number.isFinite(prev) || !Number.isFinite(next)) continue;
    const delta = next - prev;
    if (delta > thresholdMs) {
      gapCount += 1;
      largestGapMs = Math.max(largestGapMs, delta);
    }
  }
  return { hasGap: gapCount > 0, gapCount, largestGapMs };
}

function stageState(
  snap: AgentSnapshot,
  stageId: string,
  event: ObservabilityEvent | null,
  hasAnyEvents: boolean,
): WorkflowNodeState {
  if (snap.data_mode === "unavailable") return "UNAVAILABLE";
  if (!hasAnyEvents && snap.data_mode !== "fixture") return "UNAVAILABLE";

  if (snap.agent_status === "HALTED" && (stageId === "risk" || stageId === "intent")) {
    return "HALTED";
  }
  if (!event) {
    if (snap.agent_status === "OFFLINE" || snap.agent_status === "UNKNOWN") return "UNKNOWN";
    return "IDLE";
  }
  if (event.event_type === "risk.blocked") return "BLOCKED";
  if (event.event_type === "risk.halted" || event.event_type === "agent.halted") return "HALTED";
  if (event.event_type === "agent.error") return "FAILED";
  if (event.event_type === "order.reconciliation_required") return "UNKNOWN";

  const last = snap.events.length ? snap.events[snap.events.length - 1] : null;
  const isCurrent =
    last != null &&
    STAGE_DEFS.find((s) => s.id === stageId)?.eventTypes.includes(last.event_type);

  if (isCurrent && !snap.heartbeat_stale && snap.agent_status === "RUNNING") {
    return "ACTIVE";
  }
  return "COMPLETED";
}

function statusLabel(snap: AgentSnapshot, analyzing: boolean): string {
  if (snap.data_mode === "unavailable") return "Disconnected from worker telemetry";
  if (snap.agent_status === "HALTED") return "Authoritative halt observed";
  if (snap.agent_status === "OFFLINE" || snap.heartbeat_stale) return "Agent disconnected / stale heartbeat";
  if (snap.agent_status === "UNKNOWN") return "Insufficient evidence to classify agent status";
  if (snap.pipeline_blocked || snap.risk_verdict === "BLOCKED") {
    return snap.pipeline_block_reason || snap.risk_reasons[0] || "Risk blocked proposed trade";
  }
  if (analyzing) return "Analysis evidence received for the latest cycle";
  if (snap.signal_action === "HOLD") return "Last analysis completed with HOLD";
  if (snap.signal_action === "BUY" || snap.signal_action === "SELL") {
    return `Last signal ${snap.signal_action}`;
  }
  if (snap.agent_status === "RUNNING") return "Waiting for next confirmed candle";
  if (snap.agent_status === "IDLE") return "Worker healthy but idle";
  return "Status unknown";
}

export function projectStudio(snapshot: AgentSnapshot): StudioProjection {
  const events = sortEventsChronological(dedupeEvents(snapshot.events));
  const hasAnyEvents = events.length > 0;
  const analyzing = events.some((e) => e.event_type === "analysis.completed") && !snapshot.heartbeat_stale;
  const strategy = extractStrategyEvidence(events);
  const candleTimes = new Set(snapshot.candles.map((c) => c.time));
  const signalEvent = latestMatching(events, ["signal.generated"]);
  const chartFocusTime = chartTimeForEvent(signalEvent, candleTimes);

  const stages: WorkflowStage[] = STAGE_DEFS.map((def) => {
    const event = latestMatching(events, def.eventTypes);
    const state = stageState(snapshot, def.id, event, hasAnyEvents);
    return {
      id: def.id,
      step: def.step,
      label: def.label,
      description: def.description,
      state,
      timestamp: event?.occurred_at ?? null,
      summary: event?.message || (state === "UNAVAILABLE" ? "Evidence unavailable" : "No evidenced activity"),
      eventIds: events.filter((e) => def.eventTypes.includes(e.event_type)).map((e) => e.event_id),
    };
  });

  const evidenceFreshness =
    snapshot.data_mode === "unavailable"
      ? "unavailable"
      : snapshot.heartbeat_stale
        ? "stale"
        : "fresh";

  return {
    dataMode: snapshot.data_mode,
    agentStatus: snapshot.agent_status,
    heartbeatAt: snapshot.heartbeat_at ?? null,
    heartbeatStale: snapshot.heartbeat_stale,
    analyzing,
    statusLabel: statusLabel(snapshot, analyzing),
    evidenceFreshness,
    symbol: snapshot.symbol,
    interval: snapshot.interval,
    executionMode: snapshot.execution_mode,
    signalAction: snapshot.signal_action ?? null,
    signalReason: snapshot.signal_reason ?? null,
    riskVerdict: snapshot.risk_verdict,
    riskReasons: snapshot.risk_reasons,
    emaFast: snapshot.ema_fast ?? null,
    emaSlow: snapshot.ema_slow ?? null,
    rsi: snapshot.rsi ?? null,
    lastConfirmedCandleAt: snapshot.last_confirmed_candle_at ?? null,
    strategy,
    chartFocusTime,
    stages,
    events,
    orders: snapshot.orders,
    notes: snapshot.notes,
    snapshot,
  };
}

export function sliceEventsForReplay(
  events: ObservabilityEvent[],
  indexInclusive: number,
): ObservabilityEvent[] {
  if (indexInclusive < 0) return [];
  return events.slice(0, indexInclusive + 1);
}

/** Stages stay IDLE/UNAVAILABLE unless an evidenced event exists — never fake progress. */
export function hasFakeWorkflowProgress(projection: StudioProjection): boolean {
  return projection.stages.some((stage) => {
    if (stage.state === "COMPLETED" || stage.state === "ACTIVE" || stage.state === "BLOCKED") {
      return stage.eventIds.length === 0;
    }
    return false;
  });
}
