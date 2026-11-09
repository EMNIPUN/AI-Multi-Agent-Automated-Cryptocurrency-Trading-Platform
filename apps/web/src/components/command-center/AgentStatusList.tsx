import type { ElementType } from "react";

import { cn } from "@/lib/utils";

export type AgentRow = {
  name: string;
  state: string;
  icon?: ElementType;
};

export function AgentStatusList({
  agents,
  className,
}: {
  agents: AgentRow[];
  className?: string;
}) {
  return (
    <div className={cn("grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1", className)}>
      {agents.map((agent) => {
        const Icon = agent.icon;
        const state = agent.state.toUpperCase();
        const tone =
          state === "RUNNING" || state === "ACTIVE" || state === "IMPLEMENTED"
            ? "border-profit/30 bg-profit/10 text-foreground"
            : state === "ERROR" || state === "DEGRADED"
              ? "border-destructive/30 bg-destructive/10 text-destructive"
              : "border-border bg-muted/50 text-muted-foreground";
        return (
          <div
            key={agent.name}
            className={cn(
              "flex min-w-0 items-center justify-between gap-3 rounded-xl border px-3 py-2.5",
              tone,
            )}
          >
            <div className="flex min-w-0 items-center gap-2">
              {Icon ? <Icon className="h-3.5 w-3.5 shrink-0 opacity-80" /> : null}
              <span className="truncate text-sm text-foreground">{agent.name}</span>
            </div>
            <span className="shrink-0 font-mono text-[10px] uppercase tracking-wide opacity-80">
              {state}
            </span>
          </div>
        );
      })}
    </div>
  );
}
