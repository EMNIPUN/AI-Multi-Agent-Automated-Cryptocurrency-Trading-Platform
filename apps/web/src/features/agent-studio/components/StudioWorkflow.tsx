"use client";

import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { memo, useMemo } from "react";
import { motion, useReducedMotion } from "motion/react";

import { Badge } from "@/components/ui/badge";
import { BorderBeam } from "@/components/magicui/border-beam";
import { cn } from "@/lib/utils";

import type { WorkflowNodeState, WorkflowStage } from "../types";

function stateVariant(state: WorkflowNodeState) {
  if (state === "ACTIVE") return "ai" as const;
  if (state === "COMPLETED") return "success" as const;
  if (state === "BLOCKED" || state === "FAILED" || state === "HALTED") return "danger" as const;
  if (state === "UNKNOWN" || state === "WAITING") return "warning" as const;
  return "outline" as const;
}

function StudioNodeCard({ data }: NodeProps) {
  const reduce = useReducedMotion();
  const stage = data.stage as WorkflowStage;
  const selected = Boolean(data.selected);
  return (
    <div
      className={cn(
        "relative w-[200px] rounded-xl border px-3 py-2.5 shadow-sm",
        selected ? "border-primary" : "border-[#253348]",
        "bg-[#101827] text-foreground",
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-primary/60" />
      {stage.state === "ACTIVE" && !reduce ? (
        <BorderBeam size={120} duration={7} className="rounded-xl" />
      ) : null}
      <div className="flex items-start justify-between gap-2">
        <p className="text-[11px] font-medium leading-snug">{stage.label}</p>
        <Badge variant={stateVariant(stage.state)}>{stage.state}</Badge>
      </div>
      <p className="mt-1 line-clamp-2 text-[10px] text-muted-foreground">{stage.summary}</p>
      <p className="mt-1 font-mono text-[9px] text-muted-foreground">
        {stage.timestamp ? new Date(stage.timestamp).toISOString() : "no evidence"}
      </p>
      <Handle type="source" position={Position.Bottom} className="!bg-primary/60" />
    </div>
  );
}

const nodeTypes = { studio: memo(StudioNodeCard) };

export function StudioWorkflow({
  stages,
  selectedId,
  onSelect,
  demo,
}: {
  stages: WorkflowStage[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  demo?: boolean;
}) {
  const reduce = useReducedMotion();
  const nodes: Node[] = useMemo(
    () =>
      stages.map((stage, i) => {
        const col = i % 3;
        const row = Math.floor(i / 3);
        return {
          id: stage.id,
          type: "studio",
          position: { x: col * 230, y: row * 130 },
          data: { stage, selected: selectedId === stage.id },
          selected: selectedId === stage.id,
        };
      }),
    [stages, selectedId],
  );

  const edges: Edge[] = useMemo(
    () =>
      stages.slice(0, -1).map((stage, i) => {
        const next = stages[i + 1];
        const active =
          !reduce &&
          (stage.state === "ACTIVE" ||
            stage.state === "COMPLETED" ||
            next.state === "ACTIVE");
        return {
          id: `e-${stage.id}-${next.id}`,
          source: stage.id,
          target: next.id,
          animated: Boolean(active && next.state === "ACTIVE"),
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
          style: { stroke: active ? "hsl(160 84% 39% / 0.7)" : "hsl(217 25% 32%)" },
        };
      }),
    [stages, reduce],
  );

  return (
    <motion.div
      layout
      className="relative h-[420px] w-full overflow-hidden rounded-xl border border-[#253348] bg-[#080D19]"
    >
      {demo ? (
        <div className="absolute right-2 top-2 z-10">
          <Badge variant="sample">SAMPLE WORKFLOW</Badge>
        </div>
      ) : null}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, node) => onSelect(node.id)}
        onPaneClick={() => onSelect("")}
      >
        <Background gap={18} size={1} color="hsl(217 25% 18%)" />
        <MiniMap pannable zoomable maskColor="hsl(222 47% 6% / 0.7)" className="!bg-card" />
        <Controls showInteractive={false} />
      </ReactFlow>
      <div className="absolute bottom-2 left-2 flex flex-wrap gap-1">
        {stages.map((stage) => (
          <button
            key={stage.id}
            type="button"
            className={cn(
              "rounded border px-2 py-1 text-[10px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              selectedId === stage.id
                ? "border-primary bg-primary/15 text-primary"
                : "border-[#253348] text-muted-foreground hover:text-foreground",
            )}
            onClick={() => onSelect(stage.id)}
          >
            {stage.label.split(" ")[0]}
          </button>
        ))}
      </div>
    </motion.div>
  );
}
