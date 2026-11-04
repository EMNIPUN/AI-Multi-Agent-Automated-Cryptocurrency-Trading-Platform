import type {
  AgentRuntimeStatus,
  AgentSnapshot,
  DataMode,
  ExecutionMode,
  ObservabilityEvent,
  OrderLifecycleItem,
  PipelineStep,
} from "@/lib/observability/types";

export type StudioViewMode = "live" | "sample" | "replay";
export type ExplainMode = "simple" | "advanced";

export type WorkflowNodeState =
  | "IDLE"
  | "WAITING"
  | "ACTIVE"
  | "COMPLETED"
  | "BLOCKED"
  | "FAILED"
  | "HALTED"
  | "UNKNOWN"
  | "UNAVAILABLE";

export type EventCategory =
  | "MARKET"
  | "ANALYSIS"
  | "SIGNAL"
  | "RISK"
  | "ORDER"
  | "SYSTEM"
  | "ERROR";

export interface WorkflowStage {
  id: string;
  step: PipelineStep | "execution";
  label: string;
  description: string;
  state: WorkflowNodeState;
  timestamp: string | null;
  summary: string;
  eventIds: string[];
}

export interface StudioProjection {
  dataMode: DataMode;
  agentStatus: AgentRuntimeStatus;
  heartbeatAt: string | null;
  heartbeatStale: boolean;
  analyzing: boolean;
  statusLabel: string;
  symbol: string;
  interval: string;
  executionMode: ExecutionMode;
  signalAction: "BUY" | "SELL" | "HOLD" | null;
  signalReason: string | null;
  riskVerdict: AgentSnapshot["risk_verdict"];
  riskReasons: string[];
  emaFast: number | null;
  emaSlow: number | null;
  rsi: number | null;
  lastConfirmedCandleAt: string | null;
  stages: WorkflowStage[];
  events: ObservabilityEvent[];
  orders: OrderLifecycleItem[];
  notes: string[];
  snapshot: AgentSnapshot;
}
