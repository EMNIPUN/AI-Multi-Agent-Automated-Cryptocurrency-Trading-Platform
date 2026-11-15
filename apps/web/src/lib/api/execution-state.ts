/**
 * Runtime execution state derived from backend facts only.
 *
 * Sources:
 *  - GET /api/automation/status  (Phase 6A gates + MAINNET path)
 *  - GET /api/orchestrator/status (paper supervisor + live_mutate_allowed)
 *  - GET /api/orchestrator/risk   (paper risk halt)
 *  - GET /api/market/status       (public market connection)
 *
 * Nothing here authorizes anything; it only describes what the server reports.
 */

import { getJson, type ApiResult } from "@/lib/api/client";
import type { OrchestratorStatus, RiskFeed } from "@/lib/api/orchestrator";
import type { MarketStatusView } from "@/lib/market/types";

export type AutomationStatus = {
  mode?: string;
  testnet_trading_enabled?: boolean;
  testnet_operator_approved?: boolean;
  testnet_order_submission_approved?: boolean;
  testnet_mode_armed?: boolean;
  order_submission_allowed?: boolean;
  mainnet_trading_enabled?: boolean;
  mainnet_execution_path_exists?: boolean;
  bybit_testnet_env?: boolean;
  bybit_demo_env?: boolean;
  paper_autotrade_enabled?: boolean;
  human_approve_per_order?: boolean;
  live_orders?: boolean;
  mainnet_locked?: boolean;
  note?: string;
};

export type LiveLane = "locked" | "armed_approve_required";
export type TestnetLane = "off" | "armed";

export type ExecutionState = {
  /** Paper lane is always present; this reports whether the supervisor feature is on. */
  paperSupervisorEnabled: boolean;
  supervisorState: string;
  sessionId: string | null;
  workerRunning: boolean;
  heartbeatMs: number | null;
  testnet: TestnetLane;
  live: LiveLane;
  bybitEnv: "mainnet" | "testnet" | "demo" | "unknown";
  riskHalted: boolean;
  riskHaltReason: string | null;
  marketConnection: string;
  marketStale: boolean;
  /** Which sources answered. */
  sources: { automation: boolean; orchestrator: boolean; risk: boolean; market: boolean };
  fetchedAt: number;
};

export async function fetchExecutionState(init?: RequestInit): Promise<ApiResult<ExecutionState>> {
  const [auto, orch, risk, market] = await Promise.all([
    getJson<AutomationStatus>("/api/automation/status", init),
    getJson<OrchestratorStatus>("/api/orchestrator/status", init),
    getJson<RiskFeed>("/api/orchestrator/risk", init),
    getJson<MarketStatusView>("/api/market/status", init),
  ]);
  if ([auto, orch, risk, market].some((r) => !r.ok && r.code === "aborted")) {
    return { ok: false, status: 0, code: "aborted", message: "Request cancelled", at: Date.now() };
  }
  if (!auto.ok && !orch.ok && !risk.ok && !market.ok) {
    return orch.ok ? orch : (auto.ok ? auto : (orch as ApiResult<never>));
  }
  const a = auto.ok ? auto.data : null;
  const o = orch.ok ? orch.data : null;
  const r = risk.ok ? risk.data : null;
  const m = market.ok ? market.data : null;

  const liveArmed = Boolean(o?.live_mutate_allowed ?? a?.mainnet_execution_path_exists);
  const testnetArmed = Boolean(a?.testnet_mode_armed || (a?.testnet_trading_enabled && a?.testnet_order_submission_approved));
  const bybitEnv: ExecutionState["bybitEnv"] = a
    ? a.bybit_demo_env
      ? "demo"
      : a.bybit_testnet_env
        ? "testnet"
        : "mainnet"
    : o?.bybit_mainnet
      ? "mainnet"
      : "unknown";

  return {
    ok: true,
    status: 200,
    at: Date.now(),
    data: {
      paperSupervisorEnabled: Boolean(o?.enabled),
      supervisorState: String(o?.state || (o ? "STOPPED" : "UNKNOWN")).toUpperCase(),
      sessionId: o?.session_id ?? null,
      workerRunning: Boolean(o?.worker_running),
      heartbeatMs: o?.heartbeat_ms ?? null,
      testnet: testnetArmed ? "armed" : "off",
      live: liveArmed ? "armed_approve_required" : "locked",
      bybitEnv,
      riskHalted: Boolean(r?.halted),
      riskHaltReason: r?.halt_reason ?? null,
      marketConnection: String(m?.connection_state || "unknown"),
      marketStale: Boolean(m?.stale),
      sources: { automation: auto.ok, orchestrator: orch.ok, risk: risk.ok, market: market.ok },
      fetchedAt: Date.now(),
    },
  };
}
