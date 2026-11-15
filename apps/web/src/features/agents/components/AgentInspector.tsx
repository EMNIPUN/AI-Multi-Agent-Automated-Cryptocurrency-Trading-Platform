"use client";

import { DataFreshness, ReasonList, StatusIndicator } from "@/components/design-system";
import type { AgentGraphNode } from "@/features/agents/lib/agent-graph";
import { agentTimeline } from "@/features/agents/lib/agent-graph";
import type { DecisionQueueItem, RuntimeAgentStatus } from "@/lib/api/orchestrator";
import { formatDateTime, formatRelative } from "@/lib/formatting/time";

export function AgentInspector({
  node,
  runtime,
  queue,
  heartbeatMs,
}: {
  node: AgentGraphNode | null;
  runtime: RuntimeAgentStatus | null;
  queue: DecisionQueueItem[];
  heartbeatMs: number | null;
}) {
  if (!node) {
    return (
      <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-xs text-muted-foreground">
        Select a node in the graph to inspect its latest evidence, reason codes, errors and recent execution timeline.
      </div>
    );
  }
  const timeline = agentTimeline(node.id, queue);
  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-base font-medium text-foreground">{node.label}</h3>
          <StatusIndicator status={node.status} />
          {runtime?.timed_out ? <StatusIndicator status="FAILED" label="Timed out" /> : null}
          {runtime?.error ? <StatusIndicator status="FAILED" label={`Error · ${runtime.error}`} /> : null}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{runtime?.role || node.detail || "—"}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <DataFreshness at={heartbeatMs} staleAfterMs={180_000} label="heartbeat" missingLabel="No heartbeat" />
          {runtime?.source ? <span className="font-mono">source: {runtime.source}</span> : null}
          {runtime?.places_orders === false ? <span>never places orders</span> : null}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg border border-border bg-muted/40 px-2.5 py-2">
          <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">Bias / verdict</dt>
          <dd className="mt-0.5 font-mono text-foreground">{node.bias ?? "—"}</dd>
        </div>
        <div className="rounded-lg border border-border bg-muted/40 px-2.5 py-2">
          <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">Confidence</dt>
          <dd className="mt-0.5 font-mono text-foreground">{node.confidence != null ? `${Math.round(node.confidence * 100)}%` : "—"}</dd>
        </div>
      </dl>
      <p className="text-[10px] text-muted-foreground">Confidence is a qualitative weight from the pipeline — not a calibrated win probability.</p>

      {node.detail ? (
        <div>
          <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Last successful result</p>
          <p className="rounded-lg border border-border bg-muted/30 px-3 py-2 font-mono text-[11px] leading-relaxed text-foreground">{node.detail}</p>
        </div>
      ) : null}

      <div>
        <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Reason codes</p>
        <ReasonList codes={runtime?.reason_codes ?? []} />
      </div>

      <div>
        <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Recent execution timeline</p>
        {timeline.length === 0 ? (
          <p className="text-xs text-muted-foreground">No contributions in the decision ring for this node.</p>
        ) : (
          <ol className="space-y-1.5">
            {timeline.map((row) => (
              <li key={row.decision_id} className="flex items-center justify-between gap-2 rounded-lg border border-border bg-muted/30 px-2.5 py-1.5 text-xs">
                <span className="min-w-0 truncate">
                  <span className="font-mono text-foreground">{row.bias ?? "—"}</span>
                  {row.confidence != null ? <span className="text-muted-foreground"> · {Math.round(row.confidence * 100)}%</span> : null}
                  <span className="text-muted-foreground"> · decision {row.action}</span>
                  {row.timed_out ? <span className="text-loss"> · timed out</span> : null}
                  {row.error ? <span className="text-loss"> · {row.error}</span> : null}
                </span>
                <span className="shrink-0 text-[10px] text-muted-foreground" title={formatDateTime(row.timestamp_ms)}>{formatRelative(row.timestamp_ms)}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
