import { describe, expect, it } from "vitest";

import type { ChatResponse } from "@/lib/api/orchestrator";

import { conversationTitle, executedPipelineSteps, metaFromResponse, orchestrationState, responseUsesLiveLane } from "./orchestrator-state";

const base: ChatResponse = {
  reply: "ok",
  tool_calls: [],
  openai_called: false,
  llm_changed_decision: false,
  execution_allowed: false,
  live_orders: false,
  exchange_order_sent: false,
  execution_mode: "PAPER",
  preferred_mode: "PAPER",
  live_env_armed: false,
  error: null,
  conversation_id: "conv_1",
  used_fallback: false,
  fallback_reason: null,
  model: null,
  orchestration_mode: "deterministic",
  result_envelopes: [],
};

describe("orchestrationState", () => {
  it("reports openai only when the API says it was called", () => {
    expect(orchestrationState(metaFromResponse({ ...base, openai_called: true, orchestration_mode: "openai", model: "gpt-4.1-mini" }))).toBe("openai");
    expect(orchestrationState(metaFromResponse(base))).toBe("deterministic");
  });
  it("never labels a fallback as OpenAI", () => {
    const meta = metaFromResponse({ ...base, openai_called: true, used_fallback: true, fallback_reason: "llm_timeout", orchestration_mode: "fallback" });
    expect(orchestrationState(meta)).toBe("model_unavailable");
    expect(orchestrationState(metaFromResponse({ ...base, used_fallback: true, fallback_reason: "openai_spend_gate_closed" }))).toBe("budget_blocked");
    expect(orchestrationState(metaFromResponse({ ...base, used_fallback: true, fallback_reason: "other" }))).toBe("fallback");
  });
  it("surfaces tool failures, stale data and cancellation", () => {
    expect(orchestrationState(metaFromResponse({ ...base, result_envelopes: [{ tool: "x", status: "ERROR", verified: {}, model_commentary: null, error_code: "boom", reason_codes: [], call_id: null, duration_ms: 5 }] }))).toBe("tool_failed");
    expect(orchestrationState(metaFromResponse({ ...base, result_envelopes: [{ tool: "x", status: "STALE", verified: {}, model_commentary: null, error_code: null, reason_codes: [], call_id: null, duration_ms: 5 }] }))).toBe("stale");
    expect(orchestrationState({ cancelled: true })).toBe("cancelled");
  });
});

describe("live lane + titles + steps", () => {
  it("switches to the live lane only on live facts", () => {
    expect(responseUsesLiveLane(base, ["analyze_symbol"])).toBe(false);
    expect(responseUsesLiveLane(base, ["propose_live_trade"])).toBe(true);
    expect(responseUsesLiveLane({ ...base, execution_mode: "LIVE" }, [])).toBe(true);
  });
  it("titles conversations from symbol when known", () => {
    expect(conversationTitle({ conversation_id: "conv_abcdef123456", created_ms: 1, updated_ms: 2, symbol: "HYPEUSDT", interval: "15" })).toBe("HYPEUSDT · 15m");
    expect(conversationTitle({ conversation_id: "conv_abcdef123456", created_ms: 1, updated_ms: 2, symbol: null, interval: null })).toBe("Conversation abcdef12");
  });
  it("lists only executed pipeline steps from verified contributions", () => {
    const steps = executedPipelineSteps({
      tool: "run_full_analysis",
      status: "SUCCESS",
      verified: { action: "HOLD", contributions: [{ agent_id: "market_data", bias: "OK", confidence: 1 }, { agent_id: "trend", bias: "BEARISH", confidence: 0.85 }], risk: { verdict: "APPROVED" } },
      model_commentary: null,
      error_code: null,
      reason_codes: [],
      call_id: "c1",
      duration_ms: 12,
    });
    expect(steps.map((s) => s.id)).toEqual(["market_data", "trend", "coordinator", "risk"]);
    expect(steps[1].detail).toBe("BEARISH · 85%");
    expect(executedPipelineSteps({ tool: "paper_report", status: "SUCCESS", verified: { equity: "5" }, model_commentary: null, error_code: null, reason_codes: [], call_id: null, duration_ms: null })).toEqual([]);
  });
});
