"use client";

import { useMemo, useState } from "react";
import {
  CircleAlertIcon,
  CircleCheckIcon,
  LoaderCircleIcon,
  Workflow,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CodeBlock, CodeBlockContent } from "@/components/ui/code-block";
import { Shimmer } from "@/components/ui/shimmer";
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from "@/components/ui/trace";
import { cn } from "@/lib/utils";

import type { WorkflowNodeState, WorkflowStage } from "../types";

function stageStatus(state: WorkflowNodeState): "running" | "error" | "pending" | undefined {
  if (state === "ACTIVE") return "running";
  if (state === "BLOCKED" || state === "FAILED" || state === "HALTED") return "error";
  if (state === "WAITING" || state === "IDLE" || state === "UNKNOWN" || state === "UNAVAILABLE") {
    return "pending";
  }
  return undefined;
}

function stageEvidence(stage: WorkflowStage) {
  return [
    `stage: ${stage.id}`,
    `label: ${stage.label}`,
    `state: ${stage.state}`,
    `summary: ${stage.summary || "no evidence"}`,
    `description: ${stage.description || "—"}`,
    `timestamp: ${stage.timestamp ? new Date(stage.timestamp).toISOString() : "no evidence"}`,
    `events: ${stage.eventIds.length}`,
  ].join("\n");
}

function StepRow({
  stage,
  selected,
  onSelect,
  streaming,
}: {
  stage: WorkflowStage;
  selected: boolean;
  onSelect: (id: string) => void;
  streaming: boolean;
}) {
  const status = stageStatus(stage.state);
  const done = status === undefined;
  const running = status === "running" && streaming;
  const command = stage.label;

  // Match SubagentDemo StepRow: completed steps expand to CodeBlock output.
  if (done || selected || status === "error") {
    return (
      <TraceCollapsible
        open={selected}
        onOpenChange={(next) => onSelect(next ? stage.id : "")}
      >
        <TraceCollapsibleTrigger className="w-full max-w-full">
          <TraceLine status={done ? undefined : running ? "running" : status === "error" ? "error" : status}>
            <TraceIcon>
              {done ? (
                <CircleCheckIcon />
              ) : running ? (
                <LoaderCircleIcon className="animate-spin" />
              ) : status === "error" ? (
                <CircleAlertIcon />
              ) : (
                <LoaderCircleIcon className="opacity-50" />
              )}
            </TraceIcon>
            <TraceTitle>
              {done
                ? `Ran ${command}`
                : running
                  ? `Running ${command}`
                  : status === "error"
                    ? `Failed to run ${command}`
                    : `Waiting on ${command}`}
            </TraceTitle>
          </TraceLine>
        </TraceCollapsibleTrigger>
        <TraceCollapsibleContent>
          <CodeBlock size="sm">
            <CodeBlockContent wrap className="max-h-64">
              {stageEvidence(stage)}
            </CodeBlockContent>
          </CodeBlock>
        </TraceCollapsibleContent>
      </TraceCollapsible>
    );
  }

  return (
    <button type="button" className="text-left" onClick={() => onSelect(stage.id)}>
      <TraceLine status={running ? "running" : status}>
        <TraceIcon>
          {running ? (
            <LoaderCircleIcon className="animate-spin" />
          ) : (
            <LoaderCircleIcon className="opacity-40" />
          )}
        </TraceIcon>
        <TraceTitle>
          {running ? "Running" : "Waiting on"} {command}
        </TraceTitle>
      </TraceLine>
    </button>
  );
}

function SubagentRow({
  stages,
  selectedId,
  onSelect,
  streaming,
}: {
  stages: WorkflowStage[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  streaming: boolean;
}) {
  const done = stages.length > 0 && stages.every((s) => s.state === "COMPLETED");
  const failed = stages.some(
    (s) => s.state === "BLOCKED" || s.state === "FAILED" || s.state === "HALTED",
  );
  const running = !done && !failed && (streaming || stages.some((s) => s.state === "ACTIVE"));
  const report = useMemo(() => {
    const active = stages.find((s) => s.state === "ACTIVE");
    if (active) return active.summary || active.description;
    const blocked = stages.find(
      (s) => s.state === "BLOCKED" || s.state === "FAILED" || s.state === "HALTED",
    );
    if (blocked) return blocked.summary || blocked.description;
    if (done) return "The trading workflow subagent finished every stage with available evidence.";
    return "The trading workflow subagent is waiting for the next stage evidence.";
  }, [stages, done]);

  const line = (
    <TraceLine status={done ? undefined : running ? "running" : failed ? "error" : "pending"}>
      <TraceIcon>
        {done ? (
          <CircleCheckIcon />
        ) : running ? (
          <LoaderCircleIcon className="animate-spin" />
        ) : failed ? (
          <CircleAlertIcon />
        ) : (
          <Workflow />
        )}
      </TraceIcon>
      <TraceTitle>
        {done ? "Ran" : running ? "Running" : failed ? "Failed to run" : "Preparing"} the trading
        workflow subagent
      </TraceTitle>
    </TraceLine>
  );

  if (stages.length === 0) return line;

  return (
    <TraceCollapsible defaultOpen>
      <TraceCollapsibleTrigger className="w-full max-w-full">{line}</TraceCollapsibleTrigger>
      <TraceCollapsibleContent className="flex flex-col gap-3 text-foreground">
        <Trace>
          {stages.map((stage) => (
            <StepRow
              key={stage.id}
              stage={stage}
              selected={selectedId === stage.id}
              onSelect={onSelect}
              streaming={streaming}
            />
          ))}
        </Trace>
        {report ? <p className="text-sm text-foreground">{report}</p> : null}
      </TraceCollapsibleContent>
    </TraceCollapsible>
  );
}

/** Workflow panel rebuilt as Subagent Trace (replaces React Flow grid). */
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
  const [replayKey, setReplayKey] = useState(0);
  const streaming = stages.some((s) => s.state === "ACTIVE" || s.state === "WAITING");

  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-card p-5 md:p-6">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_0%,hsl(var(--primary)/0.08),transparent_40%)]" />
      <div className="relative z-10 mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-orange-300/80">
            Subagent trace
          </p>
          <h2 className="mt-1 text-lg font-medium tracking-tight text-foreground">
            Trading workflow run
          </h2>
          <p className="mt-1 text-sm text-foreground">
            Expand the subagent for each stage — same shape as the research-agent demo.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {demo ? <Badge variant="sample">SAMPLE WORKFLOW</Badge> : null}
          <Badge variant="outline" className="rounded-full">
            {stages.length} stages
          </Badge>
        </div>
      </div>

      <div
        key={replayKey}
        className="relative z-10 flex min-h-72 w-full flex-col gap-4 rounded-2xl border border-border bg-muted/70 p-4 text-sm"
      >
        {streaming ? (
          <Shimmer className="text-xs">Generating response…</Shimmer>
        ) : null}

        <Trace>
          <SubagentRow
            stages={stages}
            selectedId={selectedId}
            onSelect={onSelect}
            streaming={streaming}
          />
        </Trace>

        <div className="mt-auto flex flex-wrap items-center gap-2 pt-2">
          {stages.map((stage) => (
            <button
              key={stage.id}
              type="button"
              className={cn(
                "rounded-full border px-2.5 py-1 text-[10px] transition-colors",
                selectedId === stage.id
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border text-foreground hover:border-border hover:text-foreground",
              )}
              onClick={() => onSelect(stage.id)}
            >
              {stage.label.split(" ")[0]}
            </button>
          ))}
          <Button
            variant="outline"
            size="sm"
            className="ml-auto rounded-full"
            onClick={() => {
              onSelect("");
              setReplayKey((k) => k + 1);
            }}
          >
            Replay
          </Button>
        </div>
      </div>
    </div>
  );
}
