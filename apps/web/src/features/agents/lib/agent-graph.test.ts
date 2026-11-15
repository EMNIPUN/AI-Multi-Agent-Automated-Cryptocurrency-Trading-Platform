import { describe, expect, it } from "vitest";

import type { RuntimeAgentStatus } from "@/lib/api/orchestrator";

import { agentTimeline, buildAgentGraph } from "./agent-graph";

const agent = (id: string, status = "IDLE", extra: Partial<RuntimeAgentStatus> = {}): RuntimeAgentStatus => ({
  agent_id: id,
  label: id,
  role: "",
  places_orders: false,
  status,
  bias: null,
  confidence: null,
  reason_codes: [],
  explanation: null,
  timed_out: false,
  error: null,
  source: "registry_only",
  ...extra,
});

describe("buildAgentGraph", () => {
  it("renders the real spine with no decision", () => {
    const { nodes, edges } = buildAgentGraph([agent("market"), agent("trend"), agent("risk")], null, "STOPPED");
    expect(nodes.map((n) => n.id)).toEqual(["market", "trend", "momentum", "volume", "structure", "regime", "news", "strategy", "risk", "execution", "outcome"]);
    expect(nodes.find((n) => n.id === "outcome")?.label).toBe("No decision yet");
    expect(edges.find((e) => e.id === "news-strategy")?.dashed).toBe(true);
    expect(edges.every((e) => !e.active)).toBe(true);
  });
  it("marks blocked outcomes from the verified risk verdict", () => {
    const latest = {
      decision_id: "dec_1",
      action: "BUY",
      timestamp_ms: 1,
      explanation: "x",
      signal_strength: 0.6,
      market_quality: 1,
      reason_codes: ["COORD_BUY", "TREND_CONFLICT_VETO"],
      contributions: [{ agent_id: "trend", bias: "BEARISH", confidence: 0.85, explanation: "", reason_codes: [] }],
      risk: { verdict: "VETO", explanation: "BUY vetoed against BEARISH trend" },
      market: { data_fresh: true, last_price: 1, newest_close_ms: 1, bar_count: 219 },
    };
    const { nodes, edges } = buildAgentGraph([agent("trend", "ACTIVE", { bias: "BEARISH", confidence: 0.85 })], latest, "RUNNING");
    expect(nodes.find((n) => n.id === "risk")?.status).toBe("BLOCKED");
    expect(nodes.find((n) => n.id === "outcome")?.label).toBe("BLOCKED (VETO)");
    expect(edges.find((e) => e.id === "risk-execution")?.active).toBe(false);
    expect(edges.find((e) => e.id === "trend-strategy")?.active).toBe(true);
  });
});

describe("agentTimeline", () => {
  it("collects an agent's contributions newest first", () => {
    const queue = [
      { decision_id: "a", timestamp_ms: 1, action: "HOLD", symbol: "X", category: "linear", interval: "15", signal_strength: 0.1, directional_conviction: 0, explanation: "", reason_codes: [], risk_verdict: "APPROVED", levels: null, contributions: [{ agent_id: "trend", bias: "NEUTRAL", confidence: 0.25, explanation: "", reason_codes: ["MIXED_STRUCTURE"] }], strategy_version: null, calibration_profile_id: null, score_kind: null },
      { decision_id: "b", timestamp_ms: 2, action: "BLOCKED", symbol: "X", category: "linear", interval: "15", signal_strength: 0.5, directional_conviction: -0.5, explanation: "", reason_codes: [], risk_verdict: "VETO", levels: null, contributions: [{ agent_id: "trend", bias: "BEARISH", confidence: 0.85, explanation: "", reason_codes: ["EMA_STACK_BEAR"] }], strategy_version: null, calibration_profile_id: null, score_kind: null },
    ];
    const rows = agentTimeline("trend", queue);
    expect(rows.map((r) => r.decision_id)).toEqual(["b", "a"]);
    expect(rows[0].bias).toBe("BEARISH");
    expect(agentTimeline("risk", queue)[0].bias).toBe("VETO");
    expect(agentTimeline("volume", queue)).toEqual([]);
  });
});
