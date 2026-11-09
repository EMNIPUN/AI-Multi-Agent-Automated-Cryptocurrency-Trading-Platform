"use client";

import { RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { NumberTicker } from "@/components/magicui/number-ticker";
import { cn } from "@/lib/utils";

export type ChatExecutionMode = "PAPER" | "LIVE";

export function OrchestratorStatusStrip({
  chatMode,
  liveArmed,
  supervisorState,
  supervisorOn,
  equityNum,
  currency,
  openPositions,
  refreshing,
  sending,
  onRefresh,
  onHalt,
}: {
  chatMode: ChatExecutionMode;
  liveArmed: boolean;
  supervisorState: string;
  supervisorOn: boolean;
  equityNum: number | null;
  currency: string;
  openPositions: number;
  refreshing: boolean;
  sending: boolean;
  onRefresh: () => void;
  onHalt: () => void;
}) {
  const liveLabel = liveArmed ? "LIVE ARMED" : "LIVE GATES OFF";
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-3 py-1.5 md:px-4">
      <Badge
        variant="outline"
        className={cn(
          "rounded-full font-mono text-[11px]",
          supervisorState === "RUNNING"
            ? "border-profit/40 bg-profit/10 text-foreground"
            : "border-border bg-muted text-muted-foreground",
        )}
      >
        {supervisorState}
        {supervisorOn ? " · on" : " · off"}
      </Badge>

      <Badge
        variant="outline"
        className={cn(
          "rounded-full font-mono text-[11px]",
          chatMode === "PAPER"
            ? "border-brand/40 bg-brand/10 text-foreground"
            : "border-border bg-muted text-muted-foreground",
        )}
      >
        PAPER
      </Badge>
      <Badge
        variant="outline"
        className={cn(
          "rounded-full font-mono text-[11px]",
          chatMode === "LIVE"
            ? "border-rose-400/50 bg-rose-400/15 text-destructive"
            : liveArmed
              ? "border-rose-400/30 bg-rose-400/5 text-foreground"
              : "border-border bg-muted text-muted-foreground",
        )}
      >
        {chatMode === "LIVE" ? "LIVE · ACTIVE" : liveLabel}
      </Badge>

      <span className="hidden h-4 w-px bg-border sm:block" aria-hidden />

      <div className="flex min-w-0 items-baseline gap-1.5 text-sm">
        <span className="text-xs text-muted-foreground">Equity</span>
        {equityNum != null && Number.isFinite(equityNum) ? (
          <span className="font-mono font-medium text-foreground">
            <NumberTicker value={equityNum} decimalPlaces={2} />{" "}
            <span className="text-xs text-muted-foreground">{currency}</span>
          </span>
        ) : (
          <span className="font-mono text-muted-foreground">— {currency}</span>
        )}
      </div>

      <div className="flex items-baseline gap-1.5 text-sm">
        <span className="text-xs text-muted-foreground">Open</span>
        <span className="font-mono font-medium text-foreground">
          <NumberTicker value={openPositions} />
        </span>
      </div>

      <div className="ml-auto flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="rounded-full"
          onClick={onRefresh}
          disabled={refreshing}
        >
          {refreshing ? (
            <Spinner className="mr-1 size-3.5" />
          ) : (
            <RefreshCw className="mr-1 h-3.5 w-3.5" />
          )}
          Refresh
        </Button>
        <Button
          type="button"
          variant="destructive"
          size="sm"
          className="rounded-full"
          disabled={sending}
          onClick={onHalt}
        >
          Halt
        </Button>
      </div>
    </div>
  );
}
