"use client";

import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Badge } from "@/components/ui/badge";
import type { PipelineStep } from "@/lib/observability/types";

const STEPS: { id: string; label: string; step: PipelineStep | "execution" }[] = [
  { id: "1", label: "Bybit Market Data", step: "market_data" },
  { id: "2", label: "Confirmed Candle", step: "confirmed_candle" },
  { id: "3", label: "Strategy Analysis", step: "strategy" },
  { id: "4", label: "Signal Proposal", step: "signal" },
  { id: "5", label: "Risk Engine", step: "risk" },
  { id: "6", label: "Order Intent", step: "intent" },
  { id: "7", label: "Execution / Simulation", step: "execution" },
  { id: "8", label: "Fill Reconciliation", step: "reconciliation" },
  { id: "9", label: "Position Tracking", step: "position" },
];

function activeIndex(current: PipelineStep): number {
  if (current === "blocked" || current === "halted") return 4;
  if (current === "unknown") return -1;
  const map: Record<string, number> = {
    market_data: 0,
    confirmed_candle: 1,
    strategy: 2,
    signal: 3,
    risk: 4,
    intent: 5,
    reconciliation: 7,
    position: 8,
  };
  return map[current] ?? -1;
}

export function AgentWorkflowFlow({
  current,
  blocked,
  demo = true,
}: {
  current: PipelineStep;
  blocked?: boolean;
  demo?: boolean;
}) {
  const idx = activeIndex(current);
  const nodes: Node[] = STEPS.map((s, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const isActive = i === idx;
    const isPast = idx >= 0 && i < idx;
    const isBlockedNode = Boolean(blocked) && (s.step === "risk" || s.step === "intent");
    return {
      id: s.id,
      position: { x: col * 220, y: row * 120 },
      data: {
        label: (
          <div className="space-y-1 text-left">
            <div className="text-[11px] font-medium">{s.label}</div>
            {isBlockedNode ? (
              <Badge variant="danger">BLOCKED</Badge>
            ) : isActive ? (
              <Badge variant="ai">ACTIVE</Badge>
            ) : isPast ? (
              <Badge variant="secondary">DONE</Badge>
            ) : (
              <Badge variant="outline">IDLE</Badge>
            )}
          </div>
        ),
      },
      style: {
        width: 190,
        borderRadius: 12,
        border: isBlockedNode
          ? "1px solid hsl(0 72% 51% / 0.7)"
          : isActive
            ? "1px solid hsl(160 84% 39% / 0.8)"
            : "1px solid hsl(217 25% 22%)",
        background: "hsl(222 40% 10%)",
        color: "hsl(210 40% 96%)",
        fontSize: 12,
        padding: 10,
      },
    };
  });

  const edges: Edge[] = STEPS.slice(0, -1).map((s, i) => ({
    id: `e${s.id}-${STEPS[i + 1].id}`,
    source: s.id,
    target: STEPS[i + 1].id,
    animated: i === idx - 1 || i === idx,
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { stroke: "hsl(217 25% 40%)" },
  }));

  return (
    <div className="relative h-[360px] w-full overflow-hidden rounded-xl border border-border">
      {demo ? (
        <div className="absolute right-2 top-2 z-10">
          <Badge variant="sample">DEMO WORKFLOW</Badge>
        </div>
      ) : null}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background gap={18} size={1} color="hsl(217 25% 18%)" />
        <MiniMap
          pannable
          zoomable
          maskColor="hsl(222 47% 6% / 0.7)"
          className="!bg-card"
        />
        <Controls showInteractive={false} />
      </ReactFlow>
      <p className="absolute bottom-2 left-2 text-[10px] text-muted-foreground">
        ACCEPTED ≠ FILLED · BLOCKED/UNKNOWN/HALTED are explicit · no optimistic fills
      </p>
    </div>
  );
}
