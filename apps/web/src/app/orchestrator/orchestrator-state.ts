import type { ChatResponse, ConversationSummary, ToolResultEnvelope } from "@/lib/api/orchestrator";
import type { ReplyPayload } from "./OrchestratorReply";

export type ChatExecutionMode = "PAPER" | "LIVE";

export type TurnMeta = {
  toolNames?: string[];
  envelopes?: ToolResultEnvelope[];
  openaiCalled?: boolean;
  error?: string | null;
  model?: string | null;
  orchestrationMode?: string | null;
  usedFallback?: boolean;
  fallbackReason?: string | null;
  cancelled?: boolean;
  exchangeOrderSent?: boolean;
  liveEnvArmed?: boolean;
};

export type ChatTurn = {
  id: string;
  role: "user" | "assistant";
  text: string;
  at: number;
  payload?: ReplyPayload;
  meta?: TurnMeta;
};

export type OrchestrationState =
  | "openai"
  | "fallback"
  | "deterministic"
  | "budget_blocked"
  | "model_unavailable"
  | "tool_failed"
  | "stale"
  | "cancelled";

export const ORCHESTRATION_LABEL: Record<OrchestrationState, { label: string; tone: "ok" | "warn" | "danger" | "neutral" | "info" }> = {
  openai: { label: "OpenAI", tone: "ok" },
  fallback: { label: "LocalPlanner fallback", tone: "warn" },
  deterministic: { label: "Deterministic", tone: "info" },
  budget_blocked: { label: "API budget blocked", tone: "danger" },
  model_unavailable: { label: "Model unavailable", tone: "danger" },
  tool_failed: { label: "Tool failed", tone: "danger" },
  stale: { label: "Data stale", tone: "warn" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

const BUDGET_CODES = new Set(["openai_spend_gate_closed", "openai_budget_exhausted", "budget_exhausted", "spend_gate_closed", "daily_budget_exhausted", "monthly_budget_exhausted"]);
const MODEL_CODES = new Set(["llm_timeout", "llm_unavailable", "openai_unavailable", "model_unavailable", "openai_error"]);

/** Collapse a reply's telemetry into one honest state for the badge. */
export function orchestrationState(meta: TurnMeta | undefined): OrchestrationState {
  if (!meta) return "deterministic";
  if (meta.cancelled) return "cancelled";
  const reason = String(meta.fallbackReason || meta.error || "").toLowerCase();
  const envelopes = meta.envelopes || [];
  if (envelopes.some((e) => e.status === "ERROR") || (meta.error && !meta.usedFallback && !meta.openaiCalled)) return "tool_failed";
  if (BUDGET_CODES.has(reason)) return "budget_blocked";
  if (MODEL_CODES.has(reason)) return "model_unavailable";
  if (envelopes.some((e) => e.status === "STALE")) return "stale";
  if (meta.usedFallback) return "fallback";
  if (meta.openaiCalled || meta.orchestrationMode === "openai") return "openai";
  return "deterministic";
}

/** Build turn metadata from the chat response. Only facts the API returned. */
export function metaFromResponse(body: ChatResponse): TurnMeta {
  const tools = Array.isArray(body.tool_calls)
    ? body.tool_calls.map((c) => String(c?.name || "")).filter(Boolean)
    : [];
  return {
    toolNames: tools,
    envelopes: Array.isArray(body.result_envelopes) ? body.result_envelopes : [],
    openaiCalled: Boolean(body.openai_called),
    error: body.error ? String(body.error) : null,
    model: body.model ? String(body.model) : null,
    orchestrationMode: body.orchestration_mode ? String(body.orchestration_mode) : null,
    usedFallback: Boolean(body.used_fallback),
    fallbackReason: body.fallback_reason ? String(body.fallback_reason) : null,
    exchangeOrderSent: Boolean(body.exchange_order_sent),
    liveEnvArmed: Boolean(body.live_env_armed),
  };
}

/** Merge the last tool result with top-level execution facts for the reply card. */
export function payloadFromResponse(body: ChatResponse): ReplyPayload {
  const calls = Array.isArray(body.tool_calls) ? body.tool_calls : [];
  const last = calls.length > 0 ? calls[calls.length - 1] : null;
  const base = last?.result && typeof last.result === "object" ? { ...last.result } : {};
  return {
    ...base,
    execution_mode: body.execution_mode ?? base.execution_mode,
    preferred_mode: body.preferred_mode ?? base.preferred_mode,
    live_orders: body.live_orders ?? base.live_orders,
    live_env_armed: body.live_env_armed ?? base.live_env_armed,
    exchange_order_sent: body.exchange_order_sent ?? base.exchange_order_sent,
  };
}

const LIVE_TOOLS = new Set([
  "start_futures_intake",
  "continue_futures_intake",
  "propose_live_trade",
  "propose_live_close",
  "propose_live_cancel_orders",
  "approve_live_trade",
  "reject_live_trade",
  "list_live_positions",
]);

export function responseUsesLiveLane(body: ChatResponse, tools: string[]): boolean {
  return body.execution_mode === "LIVE" || body.live_orders === true || tools.some((t) => LIVE_TOOLS.has(t));
}

export function conversationTitle(c: ConversationSummary): string {
  if (c.symbol) return `${c.symbol}${c.interval ? ` · ${c.interval}m` : ""}`;
  return `Conversation ${c.conversation_id.replace(/^conv_/, "").slice(0, 8)}`;
}

export const TOOL_LABELS: Record<string, string> = {
  supervisor_status: "Checked session status",
  analyze_symbol: "Analyzed the market",
  paper_report: "Loaded paper performance",
  supervisor_command: "Updated the supervisor",
  openai_usage: "Checked OpenAI usage",
  live_readiness: "Checked live readiness",
  hype_feasibility: "Checked risk feasibility",
  run_full_analysis: "Ran full multi-agent analysis",
  agent_status: "Checked agents",
  get_market_price: "Fetched market price",
  list_market_quotes: "Listed available quotes",
  propose_paper_trade: "Prepared a paper trade",
  approve_paper_trade: "Approved a paper trade",
  reject_paper_trade: "Rejected a paper trade",
  propose_live_trade: "Prepared a live trade",
  approve_live_trade: "Sent an approved live order",
  reject_live_trade: "Rejected a live proposal",
  propose_live_close: "Prepared a live close",
  propose_live_cancel_orders: "Prepared an order cancel",
  list_live_positions: "Checked Bybit positions",
  start_futures_intake: "Started futures order setup",
  continue_futures_intake: "Collected order details",
};

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] || name.replace(/_/g, " ");
}

/**
 * Pipeline steps an analysis tool actually executed, derived from the verified
 * contributions in its result. Nothing is listed that the backend did not report.
 */
export function executedPipelineSteps(envelope: ToolResultEnvelope): { id: string; label: string; detail: string | null }[] {
  const verified = envelope.verified || {};
  const decision = (verified.decision && typeof verified.decision === "object" ? verified.decision : verified) as Record<string, unknown>;
  const contributions = Array.isArray(decision.contributions) ? (decision.contributions as Record<string, unknown>[]) : [];
  const steps: { id: string; label: string; detail: string | null }[] = [];
  for (const c of contributions) {
    const id = String(c.agent_id || "");
    if (!id) continue;
    const bias = c.bias ? String(c.bias) : null;
    const conf = typeof c.confidence === "number" ? `${Math.round(c.confidence * 100)}%` : null;
    steps.push({ id, label: AGENT_STEP_LABEL[id] ?? id.replace(/_/g, " "), detail: [bias, conf].filter(Boolean).join(" · ") || null });
  }
  const action = decision.action ?? decision.analysis_action ?? verified.analysis_action;
  if (action) steps.push({ id: "coordinator", label: "Strategy Coordinator", detail: String(action) });
  const risk = decision.risk && typeof decision.risk === "object" ? (decision.risk as Record<string, unknown>).verdict : verified.risk_verdict;
  if (risk) steps.push({ id: "risk", label: "Risk Engine", detail: String(risk) });
  return steps;
}

const AGENT_STEP_LABEL: Record<string, string> = {
  market_data: "Market Data",
  trend: "Trend Agent",
  momentum: "Momentum Agent",
  volume: "Volume Agent",
  structure: "Structure Agent",
  regime: "Regime Agent",
};
