"use client";

import { useEffect, useState } from "react";
import { Activity, Radio, ShieldAlert, ShieldCheck } from "lucide-react";

import { StatusBadge } from "@/components/design-system";
import { cn } from "@/lib/utils";

type StatusPayload = {
  state?: string;
  enabled?: boolean;
};

type RiskPayload = {
  halted?: boolean;
  halt_reason?: string | null;
  mode?: string;
};

type AutomationPayload = {
  mode?: string;
  testnet_submission_approved?: boolean;
  testnet_trading_enabled?: boolean;
  mainnet_trading_enabled?: boolean;
  mainnet_execution_path_exists?: boolean;
  agent_allow_live?: boolean;
};

export function GlobalStatusBar({ className }: { className?: string }) {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [risk, setRisk] = useState<RiskPayload | null>(null);
  const [automation, setAutomation] = useState<AutomationPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [st, rk, auto] = await Promise.all([
          fetch("/api/orchestrator/status", { cache: "no-store" }),
          fetch("/api/orchestrator/risk", { cache: "no-store" }),
          fetch("/api/automation/status", { cache: "no-store" }),
        ]);
        const statusBody = (await st.json().catch(() => ({}))) as StatusPayload;
        const riskBody = (await rk.json().catch(() => ({}))) as RiskPayload;
        const autoBody = (await auto.json().catch(() => ({}))) as AutomationPayload;
        if (!cancelled) {
          setStatus(statusBody);
          setRisk(rk.ok ? riskBody : null);
          setAutomation(auto.ok ? autoBody : null);
        }
      } catch {
        if (!cancelled) {
          setStatus(null);
          setRisk(null);
          setAutomation(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const state = String(status?.state || "UNKNOWN").toUpperCase();
  const supervisorOn = Boolean(status?.enabled);
  const testnetArmed = Boolean(
    automation?.testnet_submission_approved && automation?.testnet_trading_enabled,
  );
  const liveArmed = Boolean(automation?.mainnet_execution_path_exists);
  const halted = Boolean(risk?.halted);

  return (
    <div
      className={cn(
        "flex shrink-0 flex-wrap items-center gap-2 border-b border-border/60 bg-muted/30 px-3 py-1.5 text-[11px] md:px-5",
        className,
      )}
      role="status"
      aria-label="Global trading status"
    >
      <StatusBadge label="PAPER" tone="paper" />
      <StatusBadge
        label={testnetArmed ? "TESTNET armed" : "TESTNET off"}
        tone={testnetArmed ? "ok" : "neutral"}
      />
      <StatusBadge
        label={liveArmed ? "LIVE approval required" : "LIVE off"}
        tone={liveArmed ? "live" : "neutral"}
      />
      {liveArmed ? (
        <span className="inline-flex items-center gap-1 text-muted-foreground">
          <ShieldCheck className="h-3 w-3" aria-hidden />
          Chat Approve required
        </span>
      ) : null}
      {halted ? (
        <span className="inline-flex items-center gap-1 text-destructive">
          <ShieldAlert className="h-3 w-3" aria-hidden />
          Risk halt{risk?.halt_reason ? `: ${String(risk.halt_reason)}` : ""}
        </span>
      ) : null}
      <span className="hidden h-3 w-px bg-border sm:block" aria-hidden />
      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
        <Activity className="h-3 w-3" aria-hidden />
        Supervisor {state}
        {supervisorOn ? " · on" : " · off"}
      </span>
      <span className="ml-auto inline-flex items-center gap-1 text-muted-foreground">
        <Radio className="h-3 w-3" aria-hidden />
        Control · /orchestrator
      </span>
    </div>
  );
}
