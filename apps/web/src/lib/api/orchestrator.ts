/**
 * Typed contracts + fetchers for `/api/orchestrator/*` (operator-local proxy
 * to FastAPI `apps/api/app/orchestrator/router.py`).
 *
 * Shapes mirror the backend payload builders:
 *  - `_status_tool`            → OrchestratorStatus
 *  - `_report_tool`            → PaperJournalReport (lib/orchestrator/autonomy)
 *  - `build_autonomy_snapshot` → AutonomySnapshot
 *  - `per_agent_runtime_status`→ AgentsRuntime
 *  - `risk_feed`               → RiskFeed
 *  - `/diagnostics`            → OrchestratorDiagnostics
 *  - `Orchestrator.handle`     → ChatResponse
 */

import { getJson, postJson, type ApiResult } from "@/lib/api/client";
import type {
  DecisionEvidence,
  PaperJournalReport,
  SessionAuthorization,
  SupervisorCommand,
  SupervisorStatus,
} from "@/lib/orchestrator/autonomy";

export type OrchestratorStatus = SupervisorStatus & {
  live_mutate_allowed?: boolean;
  live_unlocked?: boolean;
  bybit_mainnet?: boolean;
  autonomous?: boolean;
  per_trade_approval?: boolean;
  decision_queue?: DecisionQueueItem[];
  daily_loss_fraction?: string | null;
  drawdown_fraction?: string | null;
  daily_loss_limit_fraction?: string;
  drawdown_limit_fraction?: string;
  worker_polled_at_ms?: number | null;
  risk_limits?: { risk_fraction?: string; max_open_positions?: number; leverage?: string; live_locked?: boolean };
  decision_inspector?: {
    action?: string | null;
    strategy?: string | null;
    risk_verdict?: string | null;
    blockers?: string[] | string | null;
    freshness?: string | null;
  } | null;
  summary?: string;
};

export type DecisionLevels = {
  entry: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  note?: string;
};

export type DecisionQueueItem = {
  decision_id: string;
  timestamp_ms: number;
  action: string;
  symbol: string;
  category: string;
  interval: string;
  signal_strength: number | null;
  directional_conviction: number | null;
  explanation: string;
  reason_codes: string[];
  risk_verdict: string | null;
  levels: DecisionLevels | null;
  contributions: DecisionEvidence["contributions"];
  strategy_version: string | null;
  calibration_profile_id: string | null;
  score_kind: string | null;
};

export type RuntimeAgentStatus = {
  agent_id: string;
  label: string;
  role: string;
  places_orders: boolean;
  status: string;
  bias: string | null;
  confidence: number | null;
  reason_codes: string[];
  explanation: string | null;
  timed_out: boolean;
  error: string | null;
  source: "latest_decision_contribution" | "registry_only" | string;
};

export type AgentsRuntime = {
  agents: RuntimeAgentStatus[];
  agent_count: number;
  supervisor_state: string;
  paper_supervisor_enabled: boolean;
  heartbeat_ms: number;
  strategy_version: string;
  execution_mode: "PAPER";
  live_orders: false;
  honesty_note?: string;
};

export type RiskFeed = {
  mode: "PAPER";
  live_orders: false;
  execution_allowed: false;
  supervisor_state: string | null;
  halted: boolean;
  block_new_exposure: boolean;
  halt_reason: string | null;
  daily_loss_fraction: string | null;
  drawdown_fraction: string | null;
  daily_loss_limit_fraction: string;
  drawdown_limit_fraction: string;
  open_exposure_positions: number;
  equity: string | null;
  drawdown: string | null;
  peak_equity: string | null;
  cooldown_note?: string;
  source?: string;
  label?: string;
};

export type ProtectiveEvent = {
  event_id: string;
  event_type: string;
  created_ms: number | null;
  exit_reason: string | null;
  payload: Record<string, unknown>;
  protective: boolean;
};

export type AutonomySnapshot = {
  contract_version: string;
  enabled: boolean;
  mode: "PAPER";
  live_orders: false;
  strategy_version: string;
  session: {
    state: string | null;
    session_id: string | null;
    authorization: Partial<SessionAuthorization>;
    heartbeat_ms: number | null;
    worker_running: boolean;
    last_action: string | null;
    last_reason: string | null;
    last_error: string | null;
    worker_health: "ok" | "disabled" | "offline";
  };
  worker_running: boolean;
  latest_decision: DecisionEvidence | null;
  decision_queue: DecisionQueueItem[];
  open_position: NonNullable<PaperJournalReport["positions"]>[number] | null;
  position_timeline: Array<Record<string, unknown> & { timeline_kind: "open" | "closed" }>;
  protective_events: ProtectiveEvent[];
  fills_blotter: NonNullable<PaperJournalReport["recent_trades"]>;
  pending_orders: NonNullable<PaperJournalReport["pending_orders"]>;
  journal: {
    available: boolean;
    equity_source: string;
    exchange_equity_included: false;
    equity: string | null;
    realized_pnl: string | null;
    unrealized_pnl: string | null;
    fees_paid: string | null;
    drawdown: string | null;
    closed_trades: number | null;
    winning_trades: number | null;
    win_rate: number | null;
  };
  agents: AgentsRuntime;
  risk: RiskFeed;
  agent_registry: Array<{ agent_id: string; label: string; role: string; places_orders: boolean }>;
  honesty_note: string;
};

export type OpenAiUsage = {
  enabled: boolean;
  spend_approved: boolean;
  api_key_configured: boolean;
  model_configured: boolean;
  model: string | null;
  analysis_model?: string | null;
  gates_open: boolean;
  daily_budget_usd: number;
  monthly_budget_usd: number;
  total_budget_usd: number;
  spent_usd_24h: number;
  spent_usd_30d: number;
  spent_usd_total: number;
  remaining_usd_24h: number;
  remaining_usd_total: number;
  paid_calls_blocked_until_spend_approval?: boolean;
  summary?: string;
};

export type OrchestratorDiagnostics = {
  supervisor: { state: string | null; enabled: boolean; live_orders: false; per_trade_approval: boolean; autonomous: boolean };
  latest_decision: DecisionEvidence | null;
  openai: OpenAiUsage;
  tool_permission_matrix: Record<string, string[]>;
  live_orders: false;
  places_orders: false;
};

export type ToolResultEnvelope = {
  tool: string;
  status: "SUCCESS" | "PARTIAL" | "STALE" | "UNAVAILABLE" | "BLOCKED" | "ERROR";
  verified: Record<string, unknown>;
  model_commentary: string | null;
  error_code: string | null;
  reason_codes: string[];
  call_id: string | null;
  duration_ms: number | null;
};

export type ChatToolCall = {
  name: string;
  arguments?: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  error?: string | null;
};

export type ChatResponse = {
  reply: string;
  tool_calls: ChatToolCall[];
  openai_called: boolean;
  llm_changed_decision: false;
  execution_allowed: false;
  live_orders: boolean;
  exchange_order_sent: boolean;
  execution_mode: "PAPER" | "LIVE";
  preferred_mode: "PAPER" | "LIVE";
  live_env_armed: boolean;
  error: string | null;
  conversation_id: string | null;
  used_fallback: boolean;
  fallback_reason: string | null;
  model: string | null;
  orchestration_mode: "openai" | "fallback" | "deterministic" | string;
  result_envelopes: ToolResultEnvelope[];
};

export type ConversationSummary = {
  conversation_id: string;
  created_ms: number;
  updated_ms: number;
  symbol: string | null;
  interval: string | null;
};

export type ConversationMessage = {
  role: "user" | "assistant" | "system" | string;
  content: string;
  created_ms?: number;
};

export type ConversationDetail = {
  conversation: ConversationSummary & Record<string, unknown>;
  messages: ConversationMessage[];
};

// ---------------------------------------------------------------------------
// Fetchers (same-origin proxy routes under /api/orchestrator/*)
// ---------------------------------------------------------------------------

const BASE = "/api/orchestrator";

export const fetchOrchestratorStatus = (init?: RequestInit) => getJson<OrchestratorStatus>(`${BASE}/status`, init);
export const fetchPaperReport = (init?: RequestInit) => getJson<PaperJournalReport>(`${BASE}/report`, init);
export const fetchAutonomySnapshot = (init?: RequestInit) => getJson<AutonomySnapshot>(`${BASE}/autonomy`, init);
export const fetchAgentsRuntime = (init?: RequestInit) => getJson<AgentsRuntime>(`${BASE}/agents/runtime`, init);
export const fetchRiskFeed = (init?: RequestInit) => getJson<RiskFeed>(`${BASE}/risk`, init);
export const fetchDiagnostics = (init?: RequestInit) => getJson<OrchestratorDiagnostics>(`${BASE}/diagnostics`, init);
export const fetchOpenAiStatus = (init?: RequestInit) => getJson<OpenAiUsage>(`${BASE}/openai-status`, init);
export const fetchDecisions = (init?: RequestInit) =>
  getJson<{ decision_queue: DecisionQueueItem[]; latest_decision: DecisionEvidence | null; strategy_version: string | null }>(
    `${BASE}/decisions`,
    init,
  );
export const fetchConversations = (init?: RequestInit) =>
  getJson<{ conversations: ConversationSummary[] }>(`${BASE}/conversations`, init);
export const fetchConversation = (id: string, init?: RequestInit) =>
  getJson<ConversationDetail>(`${BASE}/conversations/${encodeURIComponent(id)}`, init);
export const resetConversation = (id: string) =>
  postJson<{ ok: boolean }>(`${BASE}/conversations/${encodeURIComponent(id)}/reset`, {});

export function sendChat(body: {
  message: string;
  execution_mode: "PAPER" | "LIVE";
  conversation_id?: string | null;
}): Promise<ApiResult<ChatResponse>> {
  return postJson<ChatResponse>(`${BASE}/chat`, {
    message: body.message,
    execution_mode: body.execution_mode,
    conversation_id: body.conversation_id || undefined,
  });
}

export function sendSupervisorCommand(
  command: SupervisorCommand,
  authorization?: SessionAuthorization,
): Promise<ApiResult<OrchestratorStatus>> {
  return postJson<OrchestratorStatus>(`${BASE}/command`, {
    command,
    ...(command === "start" && authorization ? { authorization } : {}),
  });
}
