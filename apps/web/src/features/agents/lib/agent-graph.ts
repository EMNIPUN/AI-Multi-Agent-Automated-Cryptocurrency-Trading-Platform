import type { DecisionQueueItem, RuntimeAgentStatus } from "@/lib/api/orchestrator";
import type { DecisionEvidence } from "@/lib/orchestrator/autonomy";

/**
 * Topology of the SignalPipeline spine as it exists in the backend:
 *
 *   market_data → trend / momentum / volume / structure / regime
 *               → strategy (coordinator) → risk → execution (paper supervisor)
 *               → outcome (journal entry | HOLD | BLOCKED)
 *
 * Advisory agents (news, llm) point at the coordinator with a dashed edge and
 * can never change BUY/SELL. Nothing here is invented: nodes are the registry
 * agents the backend reports, statuses are the runtime statuses it returns.
 */

export type GraphNodeKind = "source" | "analyst" | "coordinator" | "risk" | "execution" | "outcome" | "advisory";

export type AgentGraphNode = {
  id: string;
  label: string;
  kind: GraphNodeKind;
  status: string;
  bias: string | null;
  confidence: number | null;
  detail: string | null;
  x: number;
  y: number;
};

export type AgentGraphEdge = { id: string; source: string; target: string; dashed?: boolean; active?: boolean };

const ANALYSTS = ["trend", "momentum", "volume", "structure", "regime"] as const;
const ADVISORY = ["news"] as const;

const COLUMN_X = { source: 0, analyst: 260, coordinator: 520, risk: 780, execution: 1040, outcome: 1300 } as const;
const ROW_H = 96;

export function buildAgentGraph(
  agents: RuntimeAgentStatus[],
  latest: DecisionEvidence | DecisionQueueItem | null,
  supervisorState: string | null,
): { nodes: AgentGraphNode[]; edges: AgentGraphEdge[] } {
  const byId = new Map(agents.map((a) => [a.agent_id, a]));
  const nodes: AgentGraphNode[] = [];
  const edges: AgentGraphEdge[] = [];
  const centerY = ((ANALYSTS.length - 1) * ROW_H) / 2;

  const market = byId.get("market");
  const marketContribution = latest && "contributions" in latest ? latest.contributions.find((c) => c.agent_id === "market_data") : undefined;
  nodes.push({
    id: "market",
    label: market?.label ?? "Market Data",
    kind: "source",
    status: market?.status ?? (marketContribution ? "ACTIVE" : "IDLE"),
    bias: marketContribution?.bias ?? market?.bias ?? null,
    confidence: marketContribution?.confidence ?? market?.confidence ?? null,
    detail: marketContribution?.explanation ?? market?.explanation ?? null,
    x: COLUMN_X.source,
    y: centerY,
  });

  ANALYSTS.forEach((id, i) => {
    const a = byId.get(id);
    nodes.push({
      id,
      label: a?.label ?? id,
      kind: "analyst",
      status: a?.status ?? "UNKNOWN",
      bias: a?.bias ?? null,
      confidence: a?.confidence ?? null,
      detail: a?.explanation ?? null,
      x: COLUMN_X.analyst,
      y: i * ROW_H,
    });
    edges.push({ id: `market-${id}`, source: "market", target: id, active: Boolean(a && a.status === "ACTIVE") });
    edges.push({ id: `${id}-strategy`, source: id, target: "strategy", active: Boolean(a && a.status === "ACTIVE") });
  });

  ADVISORY.forEach((id, i) => {
    const a = byId.get(id);
    nodes.push({
      id,
      label: a?.label ?? "News Advisory",
      kind: "advisory",
      status: a?.status ?? "IDLE",
      bias: null,
      confidence: null,
      detail: "Advisory only — cannot change BUY/SELL.",
      x: COLUMN_X.analyst,
      y: (ANALYSTS.length + i) * ROW_H + 24,
    });
    edges.push({ id: `${id}-strategy`, source: id, target: "strategy", dashed: true });
  });

  const strategy = byId.get("strategy");
  const action = latest?.action ?? null;
  nodes.push({
    id: "strategy",
    label: strategy?.label ?? "Strategy Coordinator",
    kind: "coordinator",
    status: latest ? "ACTIVE" : strategy?.status ?? "IDLE",
    bias: action,
    confidence: latest && "signal_strength" in latest && latest.signal_strength != null ? latest.signal_strength : null,
    detail: latest?.explanation ?? strategy?.explanation ?? null,
    x: COLUMN_X.coordinator,
    y: centerY,
  });

  const risk = byId.get("risk");
  const riskVerdict = latest ? ("risk" in latest && latest.risk ? latest.risk.verdict : "risk_verdict" in latest ? latest.risk_verdict : null) : null;
  const riskExplanation = latest && "risk" in latest && latest.risk ? latest.risk.explanation : risk?.explanation ?? null;
  nodes.push({
    id: "risk",
    label: risk?.label ?? "Risk Engine",
    kind: "risk",
    status: riskVerdict ? (riskVerdict === "APPROVED" ? "ACTIVE" : "BLOCKED") : risk?.status ?? "IDLE",
    bias: riskVerdict ?? null,
    confidence: null,
    detail: riskExplanation,
    x: COLUMN_X.risk,
    y: centerY,
  });
  edges.push({ id: "strategy-risk", source: "strategy", target: "risk", active: Boolean(latest) });

  const execution = byId.get("execution");
  nodes.push({
    id: "execution",
    label: "Paper Supervisor",
    kind: "execution",
    status: supervisorState ?? execution?.status ?? "UNKNOWN",
    bias: null,
    confidence: null,
    detail: execution?.role ?? "PAPER broker or gated TESTNET/LIVE deny",
    x: COLUMN_X.execution,
    y: centerY,
  });
  edges.push({ id: "risk-execution", source: "risk", target: "execution", active: riskVerdict === "APPROVED" });

  const outcomeLabel = !action ? "No decision yet" : action === "BUY" || action === "SELL" ? (riskVerdict === "APPROVED" ? "Paper journal entry" : `BLOCKED (${riskVerdict ?? "veto"})`) : action;
  nodes.push({
    id: "outcome",
    label: outcomeLabel,
    kind: "outcome",
    status: !action ? "UNKNOWN" : action === "BLOCKED" || (riskVerdict && riskVerdict !== "APPROVED") ? "BLOCKED" : action === "HOLD" ? "IDLE" : "OK",
    bias: action,
    confidence: null,
    detail: latest ? `Decision ${"decision_id" in latest ? latest.decision_id.slice(0, 20) : ""}` : null,
    x: COLUMN_X.outcome,
    y: centerY,
  });
  edges.push({ id: "execution-outcome", source: "execution", target: "outcome", active: Boolean(latest) });

  return { nodes, edges };
}

/** Recent contributions of one agent across the decision ring, newest first. */
export function agentTimeline(agentId: string, queue: DecisionQueueItem[]): { decision_id: string; timestamp_ms: number; action: string; bias: string | null; confidence: number | null; reason_codes: string[]; timed_out: boolean; error: string | null }[] {
  const key = agentId === "market" ? "market_data" : agentId;
  const out: ReturnType<typeof agentTimeline> = [];
  for (const d of [...queue].reverse()) {
    if (agentId === "strategy") {
      out.push({ decision_id: d.decision_id, timestamp_ms: d.timestamp_ms, action: d.action, bias: d.action, confidence: d.signal_strength, reason_codes: d.reason_codes || [], timed_out: false, error: null });
      continue;
    }
    if (agentId === "risk") {
      out.push({ decision_id: d.decision_id, timestamp_ms: d.timestamp_ms, action: d.action, bias: d.risk_verdict, confidence: null, reason_codes: [], timed_out: false, error: null });
      continue;
    }
    const c = (d.contributions || []).find((x) => x.agent_id === key);
    if (!c) continue;
    out.push({ decision_id: d.decision_id, timestamp_ms: d.timestamp_ms, action: d.action, bias: c.bias, confidence: c.confidence, reason_codes: c.reason_codes || [], timed_out: Boolean(c.timed_out), error: c.error ?? null });
  }
  return out.slice(0, 12);
}
