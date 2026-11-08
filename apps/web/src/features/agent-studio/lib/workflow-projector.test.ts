import { describe, expect, it } from "vitest";

import { localAgentFixture } from "@/lib/fixtures/agentSnapshot";
import type { AgentSnapshot, ObservabilityEvent } from "@/lib/observability/types";

import {
  chartTimeForEvent,
  detectReplayGaps,
  extractStrategyEvidence,
  hasFakeWorkflowProgress,
  projectStudio,
  sliceEventsForReplay,
} from "./workflow-projector";

function base(overrides: Partial<AgentSnapshot> = {}): AgentSnapshot {
  return {
    ...localAgentFixture(),
    ...overrides,
  };
}

function event(
  partial: Partial<ObservabilityEvent> & Pick<ObservabilityEvent, "event_id" | "event_type">,
): ObservabilityEvent {
  return {
    schema_version: "1.0.0",
    occurred_at: new Date().toISOString(),
    env_scope: "test",
    execution_mode: "DRY_RUN",
    message: "test",
    payload: {},
    ...partial,
  };
}

describe("projectStudio", () => {
  it("does not treat RUNNING heartbeat as ANALYZING without analysis evidence", () => {
    const snap = base({
      data_mode: "live",
      sample_label: null,
      agent_status: "RUNNING",
      heartbeat_stale: false,
      pipeline_blocked: false,
      pipeline_block_reason: null,
      risk_verdict: "N/A",
      risk_reasons: [],
      signal_action: null,
      signal_reason: null,
      events: [
        event({
          event_id: "hb1",
          event_type: "agent.heartbeat",
          message: "tick",
        }),
      ],
    });
    const proj = projectStudio(snap);
    expect(proj.agentStatus).toBe("RUNNING");
    expect(proj.analyzing).toBe(false);
    expect(proj.statusLabel.toLowerCase()).toContain("waiting");
    expect(proj.evidenceFreshness).toBe("fresh");
  });

  it("keeps HOLD distinct from trades and blocks", () => {
    const snap = base({
      data_mode: "live",
      sample_label: null,
      agent_status: "RUNNING",
      heartbeat_stale: false,
      pipeline_blocked: false,
      pipeline_block_reason: null,
      signal_action: "HOLD",
      signal_reason: "no cross",
      risk_verdict: "N/A",
      risk_reasons: [],
      events: [
        event({
          event_id: "sig1",
          event_type: "signal.generated",
          message: "no cross",
          payload: {
            action: "HOLD",
            explanation_code: "HOLD_NO_CROSS",
            conditions: [{ id: "ema_cross_up", result: "FAIL" }],
          },
        }),
      ],
    });
    const proj = projectStudio(snap);
    expect(proj.signalAction).toBe("HOLD");
    expect(proj.statusLabel).toContain("HOLD");
    expect(proj.strategy.explanationCode).toBe("HOLD_NO_CROSS");
    expect(proj.strategy.conditions[0]?.result).toBe("FAIL");
  });

  it("marks unavailable when data_mode unavailable", () => {
    const proj = projectStudio(base({ data_mode: "unavailable", events: [] }));
    expect(proj.stages.every((s: { state: string }) => s.state === "UNAVAILABLE")).toBe(true);
    expect(proj.evidenceFreshness).toBe("unavailable");
  });

  it("maps blocked risk events", () => {
    const snap = base({
      data_mode: "live",
      sample_label: null,
      pipeline_blocked: true,
      risk_verdict: "BLOCKED",
      risk_reasons: ["position unknown"],
      events: [
        event({
          event_id: "rb1",
          event_type: "risk.blocked",
          message: "position unknown",
        }),
      ],
    });
    const risk = projectStudio(snap).stages.find((s: { id: string }) => s.id === "risk");
    expect(risk?.state).toBe("BLOCKED");
  });

  it("dedupes by relying on projector input order and replay slice", () => {
    const events = localAgentFixture().events;
    expect(sliceEventsForReplay(events, 1).length).toBeLessThanOrEqual(2);
    expect(sliceEventsForReplay(events, -1)).toEqual([]);
  });

  it("does not invent workflow progress without evidenced events", () => {
    const proj = projectStudio(
      base({
        data_mode: "live",
        sample_label: null,
        agent_status: "RUNNING",
        heartbeat_stale: false,
        events: [
          event({
            event_id: "hb",
            event_type: "agent.heartbeat",
          }),
        ],
      }),
    );
    expect(hasFakeWorkflowProgress(proj)).toBe(false);
    const idleOrUnknown = proj.stages.filter((s) => s.id !== "market");
    expect(idleOrUnknown.every((s) => s.state === "IDLE" || s.state === "UNKNOWN")).toBe(true);
  });
});

describe("strategy / chart alignment", () => {
  it("extracts HOLD explanation evidence", () => {
    const evidence = extractStrategyEvidence([
      event({
        event_id: "a1",
        event_type: "analysis.completed",
        payload: {
          strategy_id: "ema_rsi",
          strategy_version: "1",
          explanation_code: "HOLD_NO_CROSS",
          conditions: [{ id: "ema_cross_up", result: "FAIL" }],
        },
      }),
    ]);
    expect(evidence.explanationCode).toBe("HOLD_NO_CROSS");
    expect(evidence.strategyId).toBe("ema_rsi");
  });

  it("aligns event chart time only to verified candle opens", () => {
    const aligned = event({
      event_id: "s1",
      event_type: "signal.generated",
      payload: { candle_start_ms: 1_700_000_000_000 },
    });
    const orphan = event({
      event_id: "s2",
      event_type: "signal.generated",
      payload: { candle_start_ms: 9_999_000_000_000 },
    });
    const times = new Set([1_700_000_000]);
    expect(chartTimeForEvent(aligned, times)).toBe(1_700_000_000);
    expect(chartTimeForEvent(orphan, times)).toBeNull();
  });

  it("detects replay chronological gaps", () => {
    const events = [
      event({
        event_id: "e1",
        event_type: "agent.heartbeat",
        occurred_at: "2024-01-01T00:00:00.000Z",
      }),
      event({
        event_id: "e2",
        event_type: "agent.heartbeat",
        occurred_at: "2024-01-01T02:00:00.000Z",
      }),
    ];
    const gaps = detectReplayGaps(events, 30 * 60 * 1000);
    expect(gaps.hasGap).toBe(true);
    expect(gaps.gapCount).toBe(1);
    expect(gaps.largestGapMs).toBe(2 * 60 * 60 * 1000);
  });
});
