"use client";

import { Activity, Bot, Radio, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { ExecutionMode, StatusIndicator } from "@/components/design-system";
import { useExecutionState } from "@/providers/ExecutionStateProvider";
import { cn } from "@/lib/utils";

/**
 * Runtime execution strip. Every label comes from the shared execution-state
 * subscription (automation gates, supervisor, risk, market). Nothing here is
 * hardcoded to "locked" or "off".
 */
export function GlobalStatusBar({ className }: { className?: string }) {
  const { data, error, loading } = useExecutionState();
  const liveArmed = data?.live === "armed_approve_required";
  const testnetArmed = data?.testnet === "armed";
  const supervisor = data?.supervisorState ?? "UNKNOWN";
  const marketKind = data ? (data.marketStale ? "STALE" : data.marketConnection) : "UNKNOWN";

  return (
    <div
      className={cn(
        "flex shrink-0 flex-wrap items-center gap-2 border-b border-border/60 bg-muted/30 px-3 py-1.5 text-[11px] md:px-5",
        className,
      )}
      role="status"
      aria-label="Global trading status"
      aria-busy={loading || undefined}
    >
      <ExecutionMode mode="paper" />
      <ExecutionMode mode="testnet" armed={testnetArmed} />
      <ExecutionMode mode="live" armed={liveArmed} />
      {liveArmed ? (
        <span className="inline-flex items-center gap-1 text-muted-foreground" title={`Bybit ${data?.bybitEnv ?? "unknown"} · every live order needs an explicit Approve in chat`}>
          <ShieldCheck className="h-3 w-3" aria-hidden />
          Bybit {data?.bybitEnv ?? "unknown"}
        </span>
      ) : null}
      {data?.riskHalted ? (
        <span className="inline-flex items-center gap-1 text-destructive">
          <ShieldAlert className="h-3 w-3" aria-hidden />
          Risk halt{data.riskHaltReason ? `: ${String(data.riskHaltReason).replace(/_/g, " ")}` : ""}
        </span>
      ) : null}
      <span className="hidden h-3 w-px bg-border sm:block" aria-hidden />
      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
        <Activity className="h-3 w-3" aria-hidden />
        <StatusIndicator
          status={loading ? "UNKNOWN" : supervisor}
          label={`Supervisor ${loading ? "…" : supervisor.toLowerCase()}`}
          variant="inline"
          pulse
          detail={data ? (data.paperSupervisorEnabled ? (data.workerRunning ? "· worker on" : "· worker off") : "· feature off") : undefined}
        />
      </span>
      <span className="hidden items-center gap-1.5 text-muted-foreground md:inline-flex">
        <Radio className="h-3 w-3" aria-hidden />
        <StatusIndicator status={marketKind} label={`Market ${String(marketKind).toLowerCase().replace(/_/g, " ")}`} variant="inline" />
      </span>
      {error && !data ? (
        <span className="text-destructive">API unreachable</span>
      ) : null}
      <Link href="/orchestrator" className="ml-auto inline-flex items-center gap-1 text-muted-foreground hover:text-foreground">
        <Bot className="h-3 w-3" aria-hidden />
        Control · /orchestrator
      </Link>
    </div>
  );
}
