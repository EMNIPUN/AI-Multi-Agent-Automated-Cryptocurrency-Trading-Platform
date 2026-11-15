"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowRight, RefreshCw } from "lucide-react";

import { SectionPanel } from "@/components/command-center";
import { AiWorkspaceTemplate, DataFreshness, ErrorState, StatusIndicator } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { buildAgentGraph } from "@/features/agents/lib/agent-graph";
import { useIsMobile } from "@/hooks/use-mobile";
import { usePolledResource } from "@/hooks/use-polled-resource";
import { fetchAutonomySnapshot } from "@/lib/api/orchestrator";
import { AGENT_REGISTRY } from "@/lib/agents/registry";
import { formatRelative } from "@/lib/formatting/time";
import { cn } from "@/lib/utils";

import { AgentInspector } from "./AgentInspector";

const AgentGraph = dynamic(() => import("./AgentGraph").then((m) => m.AgentGraph), {
  ssr: false,
  loading: () => <Skeleton className="h-[440px] w-full rounded-xl" />,
});

export function AgentWorkspace() {
  const autonomy = usePolledResource(fetchAutonomySnapshot, { intervalMs: 15_000 });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const isMobile = useIsMobile();

  const snap = autonomy.data;
  const agents = useMemo(() => snap?.agents?.agents ?? [], [snap]);
  const queue = useMemo(() => snap?.decision_queue ?? [], [snap]);
  const latest = snap?.latest_decision ?? null;
  const graph = useMemo(() => buildAgentGraph(agents, latest, snap?.session.state ?? null), [agents, latest, snap?.session.state]);
  const selectedNode = graph.nodes.find((n) => n.id === selectedId) ?? null;
  const selectedRuntime = agents.find((a) => a.agent_id === (selectedId === "market" ? "market" : selectedId)) ?? null;
  const heartbeat = snap?.session.heartbeat_ms ?? null;
  const cards = agents.length > 0 ? agents : AGENT_REGISTRY.map((a) => ({ ...a, status: "UNKNOWN", bias: null, confidence: null, reason_codes: [], explanation: null, timed_out: false, error: null, source: "registry_only" }));

  const inspector = <AgentInspector node={selectedNode} runtime={selectedRuntime} queue={queue} heartbeatMs={heartbeat} />;

  return (
    <AiWorkspaceTemplate
      title="Agent Workspace"
      description="The SignalPipeline spine as the backend reports it: market data → analysts → coordinator → deterministic risk → paper supervisor. Advisory agents never change BUY/SELL."
      modes={["readonly", "paper"]}
      actions={
        <>
          <Button variant="outline" size="sm" className="rounded-full" onClick={() => void autonomy.refresh()} disabled={autonomy.refreshing}>
            <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", autonomy.refreshing && "animate-spin")} aria-hidden />
            Refresh
          </Button>
          <Button asChild variant="secondary" size="sm" className="rounded-full">
            <Link href="/agents/live">Live analysis<ArrowRight className="ml-1 h-3.5 w-3.5" aria-hidden /></Link>
          </Button>
        </>
      }
    >
      {autonomy.error && !snap ? (
        <ErrorState title="Agent runtime unavailable" code={autonomy.error.code} at={autonomy.error.at} onRetry={() => void autonomy.refresh()} retrying={autonomy.refreshing} />
      ) : null}

      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <StatusIndicator status={snap?.session.state ?? "UNKNOWN"} label={`Supervisor ${(snap?.session.state ?? "unknown").toLowerCase()}`} pulse />
        <DataFreshness at={heartbeat} staleAfterMs={180_000} label="heartbeat" missingLabel="No heartbeat" />
        <span>Strategy {snap?.strategy_version ?? "—"}</span>
        <span>· {queue.length} decision{queue.length === 1 ? "" : "s"} in ring</span>
        {latest ? <span>· last decision {formatRelative(latest.timestamp_ms)}</span> : null}
      </div>

      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(18rem,0.9fr)]">
        <SectionPanel title="Pipeline graph" description="Edges animate on nodes that contributed to the latest decision. Nothing here executes a trade." bodyClassName="min-w-0">
          {autonomy.loading && !snap ? <Skeleton className="h-[440px] w-full rounded-xl" /> : <AgentGraph nodes={graph.nodes} edges={graph.edges} selectedId={selectedId} onSelect={setSelectedId} />}
        </SectionPanel>
        <div className="hidden xl:block">
          <SectionPanel title="Agent inspector" description="Latest evidence for the selected node.">{inspector}</SectionPanel>
        </div>
      </div>

      <SectionPanel title="Registered agents" description={snap?.agents?.honesty_note ?? "Status comes from the latest decision contributions. A registered module is not an active agent."}>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {cards.map((a) => (
            <button
              key={a.agent_id}
              type="button"
              onClick={() => setSelectedId(a.agent_id === "market" ? "market" : graph.nodes.some((n) => n.id === a.agent_id) ? a.agent_id : a.agent_id === "news" ? "news" : null)}
              className={cn(
                "rounded-2xl border border-border bg-muted/30 p-4 text-left transition-colors hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                selectedId === a.agent_id && "border-brand/60 bg-brand/5",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-foreground">{a.label}</p>
                  <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">{a.agent_id}</p>
                </div>
                <StatusIndicator status={a.status} />
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{a.role}</p>
              <p className="mt-2 text-[11px] text-muted-foreground">
                {a.bias ? <span className="font-mono text-foreground">{a.bias}{a.confidence != null ? ` · ${Math.round(a.confidence * 100)}%` : ""}</span> : "No contribution in the latest decision"}
                {a.error ? <span className="text-loss"> · {a.error}</span> : null}
              </p>
            </button>
          ))}
        </div>
      </SectionPanel>

      {isMobile ? (
        <Sheet open={Boolean(selectedId)} onOpenChange={(open) => !open && setSelectedId(null)}>
          <SheetContent side="bottom" className="max-h-[85vh] overflow-y-auto rounded-t-3xl">
            <SheetHeader>
              <SheetTitle>Agent inspector</SheetTitle>
              <SheetDescription>Latest evidence for the selected node.</SheetDescription>
            </SheetHeader>
            <div className="mt-4">{inspector}</div>
          </SheetContent>
        </Sheet>
      ) : (
        <div className="xl:hidden">
          <SectionPanel title="Agent inspector" description="Latest evidence for the selected node.">{inspector}</SectionPanel>
        </div>
      )}
    </AiWorkspaceTemplate>
  );
}
