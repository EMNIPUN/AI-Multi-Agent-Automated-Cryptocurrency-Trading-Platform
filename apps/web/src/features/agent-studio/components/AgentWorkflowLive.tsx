"use client";

import { useMemo, useState } from "react";
import {
  Activity,
  Bot,
  CandlestickChart,
  CheckCircle2,
  CircleDashed,
  ShieldAlert,
  Sparkles,
  Workflow,
} from "lucide-react";

import {
  Subagent,
  SubagentContent,
  SubagentHeader,
  SubagentTool,
  SubagentTools,
} from "@/components/ai-elements/subagent";
import { Task, TaskContent, TaskItem, TaskTrigger } from "@/components/ai-elements/task";
import { Badge } from "@/components/ui/badge";
import { Shimmer } from "@/components/ui/shimmer";
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceDescription,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from "@/components/ui/trace";

import type { WorkflowNodeState, WorkflowStage } from "../types";

const ICONS: Record<string, React.ElementType> = {
  market: CandlestickChart,
  candle: CandlestickChart,
  analysis: Sparkles,
  signal: Activity,
  risk: ShieldAlert,
  intent: Workflow,
  execution: CheckCircle2,
  reconcile: CircleDashed,
  position: CheckCircle2,
};

function stageStatus(state: WorkflowNodeState): "running" | "error" | "pending" | undefined {
  if (state === "ACTIVE") return "running";
  if (state === "BLOCKED" || state === "FAILED" || state === "HALTED") return "error";
  if (state === "WAITING" || state === "IDLE" || state === "UNKNOWN" || state === "UNAVAILABLE") {
    return "pending";
  }
  return undefined;
}

function stageTitle(stage: WorkflowStage) {
  const status = stageStatus(stage.state);
  const label = stage.label || stage.id;
  if (status === "running") return `Running ${label.toLowerCase()}`;
  if (status === "error") return `Failed ${label.toLowerCase()}`;
  if (status === "pending") return `Waiting on ${label.toLowerCase()}`;
  return `Completed ${label.toLowerCase()}`;
}

function overallStatus(stages: WorkflowStage[]): "running" | "error" | "pending" | undefined {
  if (stages.some((s) => s.state === "ACTIVE")) return "running";
  if (stages.some((s) => s.state === "BLOCKED" || s.state === "FAILED" || s.state === "HALTED")) {
    return "error";
  }
  if (stages.every((s) => s.state === "COMPLETED")) return undefined;
  return "pending";
}

function overallTitle(stages: WorkflowStage[], status: ReturnType<typeof overallStatus>) {
  const done = stages.filter((s) => s.state === "COMPLETED").length;
  if (status === "running") return `Running the trading agent · ${done} of ${stages.length} done`;
  if (status === "error") return `Failed the trading agent run · ${done} of ${stages.length} done`;
  if (status === "pending") return `Preparing the trading agent · ${done} of ${stages.length} done`;
  return `Ran the trading agent · ${stages.length} steps`;
}

/** Live agent flow as shadcn Trace Task + Subagent composition. */
export function AgentWorkflowLive({
  stages,
  selectedId,
  onSelect,
}: {
  stages: WorkflowStage[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const visible = useMemo(() => stages.slice(0, 9), [stages]);
  const status = overallStatus(visible);
  const selected = stages.find((s) => s.id === selectedId) ?? null;
  const [open, setOpen] = useState<boolean>();
  const [taskOpen, setTaskOpen] = useState(true);

  const activeCount = visible.filter((s) => s.state === "ACTIVE").length;
  const failedCount = visible.filter(
    (s) => s.state === "BLOCKED" || s.state === "FAILED" || s.state === "HALTED",
  ).length;

  return (
    <div className="relative overflow-hidden rounded-3xl border border-border bg-muted/40 p-5 md:p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-orange-300/80">
            Live workflow
          </p>
          <h2 className="mt-1 text-xl font-medium tracking-tight text-foreground">
            How your agent thinks right now
          </h2>
          <p className="mt-1 text-sm text-foreground">
            Trace steps expand like tool calls — open a stage for evidence.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="outline" className="rounded-full">
            {visible.length} stages
          </Badge>
          {activeCount > 0 ? (
            <Badge variant="warning" className="rounded-full">
              {activeCount} running
            </Badge>
          ) : null}
          {failedCount > 0 ? (
            <Badge variant="danger" className="rounded-full">
              {failedCount} blocked
            </Badge>
          ) : null}
        </div>
      </div>

      <div className="rounded-2xl border border-border bg-muted/60 p-4">
        <Subagent open={open ?? status === "running"} onOpenChange={setOpen}>
          <SubagentHeader
            title={overallTitle(visible, status)}
            status={status}
            icon={<Bot className="size-4" />}
            model="CryptoNova worker"
          />
          <SubagentContent>
            {status === "running" ? (
              <Shimmer className="text-xs">Generating response…</Shimmer>
            ) : (
              <p className="text-xs text-foreground">
                Pipeline evidence from the live worker. Completed steps stay past tense; active
                steps shimmer while they run.
              </p>
            )}

            <Task open={taskOpen} onOpenChange={setTaskOpen}>
              <TaskTrigger
                title={
                  status === "running"
                    ? "Updating market → risk → execution path"
                    : status === "error"
                      ? "Failed to finish the market → risk path"
                      : "Finished market → risk → execution path"
                }
                status={status}
                icon={<Workflow className="size-4" />}
              />
              <TaskContent>
                {visible.map((stage) => {
                  const Icon = ICONS[stage.id] || Workflow;
                  const lineStatus = stageStatus(stage.state);
                  const isSelected = selectedId === stage.id;
                  return (
                    <TraceCollapsible
                      key={stage.id}
                      open={isSelected}
                      onOpenChange={(next) => {
                        if (next) onSelect(stage.id);
                        else if (isSelected) onSelect("");
                      }}
                    >
                      <TraceCollapsibleTrigger className="w-full max-w-full">
                        <TraceLine
                          status={lineStatus}
                          className={isSelected ? "text-foreground" : undefined}
                        >
                          <TraceIcon>
                            <Icon />
                          </TraceIcon>
                          <TraceTitle>{stageTitle(stage)}</TraceTitle>
                          {stage.timestamp ? (
                            <TraceDescription>
                              {new Date(stage.timestamp).toLocaleTimeString()}
                            </TraceDescription>
                          ) : null}
                        </TraceLine>
                      </TraceCollapsibleTrigger>
                      <TraceCollapsibleContent keepMounted className="text-foreground">
                        <p className="text-sm text-foreground">{stage.description}</p>
                        <p className="mt-1 text-xs text-foreground">{stage.summary}</p>
                        {stage.eventIds.length > 0 ? (
                          <p className="mt-2 text-[11px] text-foreground">
                            {stage.eventIds.length} linked evidence event
                            {stage.eventIds.length === 1 ? "" : "s"}
                          </p>
                        ) : (
                          <p className="mt-2 text-[11px] text-foreground">No linked events yet</p>
                        )}
                      </TraceCollapsibleContent>
                    </TraceCollapsible>
                  );
                })}
              </TaskContent>
            </Task>

            <SubagentTools>
              <SubagentTool
                title={
                  status === "running"
                    ? "Streaming worker telemetry"
                    : status === "error"
                      ? "Failed to keep worker telemetry fresh"
                      : "Synced worker telemetry"
                }
                status={status === "pending" ? "pending" : status}
                icon={<Activity className="size-4" />}
              />
              {selected ? (
                <TaskItem
                  title={`Inspecting ${selected.label}`}
                  status={stageStatus(selected.state)}
                  icon={<Sparkles className="size-4" />}
                />
              ) : (
                <Trace>
                  <TraceLine status="pending">
                    <TraceIcon>
                      <CircleDashed />
                    </TraceIcon>
                    <TraceTitle>Select a stage to inspect details</TraceTitle>
                  </TraceLine>
                </Trace>
              )}
            </SubagentTools>
          </SubagentContent>
        </Subagent>
      </div>
    </div>
  );
}
