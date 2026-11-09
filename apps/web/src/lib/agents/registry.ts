/** Shared agent registry aligned with backend agent_registry.REGISTRY. */

export type AgentRegistryItem = {
  agent_id: string;
  label: string;
  role: string;
  places_orders: boolean;
};

export const AGENT_REGISTRY: readonly AgentRegistryItem[] = [
  { agent_id: "market", label: "Market Data", role: "Public candles, freshness, last price", places_orders: false },
  { agent_id: "trend", label: "Technical Trend", role: "EMA / trend bias", places_orders: false },
  { agent_id: "momentum", label: "Technical Momentum", role: "RSI / momentum bias", places_orders: false },
  { agent_id: "volume", label: "Volume", role: "Relative volume and price/volume agreement", places_orders: false },
  { agent_id: "structure", label: "Market Structure", role: "Swing HH/HL vs LH/LL and range breaks", places_orders: false },
  { agent_id: "regime", label: "Regime", role: "Trend/range/volatility confirmation gate", places_orders: false },
  { agent_id: "strategy", label: "Strategy Coordinator", role: "Deterministic proposal", places_orders: false },
  { agent_id: "news", label: "News Advisory", role: "Advisory context only", places_orders: false },
  { agent_id: "portfolio", label: "Portfolio", role: "Paper equity / exposure reads", places_orders: false },
  { agent_id: "risk", label: "Risk Engine", role: "Independent veto authority", places_orders: false },
  { agent_id: "execution", label: "Execution Gateway", role: "PAPER broker or gated TESTNET/LIVE deny", places_orders: false },
  { agent_id: "performance", label: "Performance", role: "Paper journal / PnL reads", places_orders: false },
  { agent_id: "reliability", label: "Reliability", role: "Supervisor heartbeat / halt", places_orders: false },
] as const;

export type RuntimeAgent = {
  agent_id: string;
  label: string;
  status: string;
  bias?: string | null;
  confidence?: number | null;
};

export function agentsForStatusList(
  runtimeAgents: RuntimeAgent[] | null | undefined,
): { name: string; state: string }[] {
  if (runtimeAgents && runtimeAgents.length > 0) {
    return runtimeAgents.map((a) => ({
      name: a.label || a.agent_id,
      state: String(a.status || "IDLE").toUpperCase(),
    }));
  }
  return AGENT_REGISTRY.map((a) => ({ name: a.label, state: "UNKNOWN" }));
}
