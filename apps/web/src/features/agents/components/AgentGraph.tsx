"use client";

import { Background, Controls, MarkerType, MiniMap, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";

import { StatusIndicator } from "@/components/design-system";
import type { AgentGraphEdge, AgentGraphNode } from "@/features/agents/lib/agent-graph";
import { normalizeStatus } from "@/lib/formatting/status";

const KIND_LABEL: Record<AgentGraphNode["kind"], string> = {
  source: "Source",
  analyst: "Analyst",
  coordinator: "Coordinator",
  risk: "Veto authority",
  execution: "Execution lane",
  outcome: "Outcome",
  advisory: "Advisory",
};

function nodeBorder(status: string): string {
  switch (normalizeStatus(status)) {
    case "running":
    case "ok":
      return "hsl(var(--profit) / 0.7)";
    case "blocked":
      return "hsl(var(--loss) / 0.8)";
    case "failed":
      return "hsl(var(--destructive) / 0.8)";
    case "paused":
    case "stale":
      return "hsl(var(--warning) / 0.7)";
    default:
      return "hsl(var(--border))";
  }
}

function NodeLabel({ node }: { node: AgentGraphNode }) {
  return (
    <div className="space-y-1 text-left">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{KIND_LABEL[node.kind]}</p>
      <p className="truncate text-[12px] font-medium text-foreground">{node.label}</p>
      <div className="flex flex-wrap items-center gap-1">
        <StatusIndicator status={node.status} size="sm" />
        {node.bias ? (
          <span className="font-mono text-[10px] text-muted-foreground">
            {node.bias}
            {node.confidence != null ? ` · ${Math.round(node.confidence * 100)}%` : ""}
          </span>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Read-only pipeline graph. Selecting a node opens the inspector; nothing on
 * the canvas can place an order or change supervisor state.
 */
export function AgentGraph({
  nodes,
  edges,
  selectedId,
  onSelect,
  height = 440,
}: {
  nodes: AgentGraphNode[];
  edges: AgentGraphEdge[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  height?: number;
}) {
  const rfNodes = useMemo<Node[]>(
    () =>
      nodes.map((n) => ({
        id: n.id,
        position: { x: n.x, y: n.y },
        data: { label: <NodeLabel node={n} /> },
        selectable: true,
        style: {
          width: 210,
          borderRadius: 12,
          border: `1px solid ${selectedId === n.id ? "hsl(var(--brand))" : nodeBorder(n.status)}`,
          boxShadow: selectedId === n.id ? "0 0 0 2px hsl(var(--brand) / 0.35)" : "var(--panel-shadow)",
          background: n.kind === "advisory" ? "hsl(var(--muted))" : "hsl(var(--card))",
          color: "hsl(var(--foreground))",
          fontSize: 12,
          padding: 10,
          borderStyle: n.kind === "advisory" ? "dashed" : "solid",
        },
      })),
    [nodes, selectedId],
  );
  const rfEdges = useMemo<Edge[]>(
    () =>
      edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        animated: Boolean(e.active),
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: e.active ? "hsl(var(--brand))" : "hsl(var(--border-strong))" },
        style: {
          stroke: e.active ? "hsl(var(--brand))" : "hsl(var(--border-strong))",
          strokeWidth: e.active ? 1.75 : 1.25,
          strokeDasharray: e.dashed ? "4 4" : undefined,
        },
      })),
    [edges],
  );

  return (
    <div className="relative w-full overflow-hidden rounded-xl border border-border bg-muted/20" style={{ height }} role="group" aria-label="Agent pipeline graph">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        minZoom={0.35}
        maxZoom={1.6}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        panOnScroll
        onNodeClick={(_, node) => onSelect(node.id)}
        onPaneClick={() => onSelect(null)}
        colorMode="system"
        className="!bg-transparent"
      >
        <Background gap={18} size={1} color="hsl(var(--border) / 0.6)" />
        <MiniMap pannable zoomable maskColor="hsl(var(--background) / 0.7)" nodeColor={() => "hsl(var(--muted-foreground) / 0.5)"} className="!rounded-lg !border !border-border !bg-card" />
        <Controls showInteractive={false} className="!rounded-lg !border !border-border !bg-card !shadow-none [&>button]:!border-border [&>button]:!bg-card [&>button]:!text-foreground" />
      </ReactFlow>
      <p className="pointer-events-none absolute bottom-2 left-2 rounded bg-background/80 px-1.5 py-0.5 text-[10px] text-muted-foreground">
        Read-only · click a node to inspect · dashed = advisory only
      </p>
    </div>
  );
}
