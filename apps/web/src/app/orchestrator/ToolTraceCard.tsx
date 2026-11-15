"use client";

import { AlertTriangle, CheckCircle2, CircleAlertIcon, Clock3, Hourglass, ShieldOff, Wrench } from "lucide-react";

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
import type { ToolResultEnvelope } from "@/lib/api/orchestrator";
import { explainReason } from "@/lib/formatting/reason-codes";

import { executedPipelineSteps, toolLabel } from "./orchestrator-state";

function statusIcon(status: ToolResultEnvelope["status"]) {
  switch (status) {
    case "SUCCESS":
      return <CheckCircle2 className="text-profit" />;
    case "PARTIAL":
      return <AlertTriangle className="text-warning" />;
    case "STALE":
      return <Hourglass className="text-warning" />;
    case "UNAVAILABLE":
      return <CircleAlertIcon className="text-muted-foreground" />;
    case "BLOCKED":
      return <ShieldOff className="text-loss" />;
    default:
      return <CircleAlertIcon className="text-destructive" />;
  }
}

/**
 * Real tool execution trace. Every line is a `result_envelopes` entry the chat
 * API returned (tool, verified status, duration). Analysis tools expand into
 * the agents that actually contributed to the verified decision.
 */
export function ToolTraceCard({
  envelopes,
  toolNames,
  error,
}: {
  envelopes?: ToolResultEnvelope[];
  toolNames?: string[];
  error?: string | null;
}) {
  const rows: ToolResultEnvelope[] =
    envelopes && envelopes.length > 0
      ? envelopes
      : (toolNames || []).map((name) => ({
          tool: name,
          status: "SUCCESS" as const,
          verified: {},
          model_commentary: null,
          error_code: null,
          reason_codes: [],
          call_id: null,
          duration_ms: null,
        }));

  if (rows.length === 0 && !error) return null;

  const failed = rows.filter((r) => r.status === "ERROR" || r.status === "BLOCKED").length;
  const totalMs = rows.reduce((acc, r) => acc + (r.duration_ms ?? 0), 0);
  const summary =
    rows.length === 0
      ? "Request failed"
      : rows.length === 1
        ? toolLabel(rows[0].tool)
        : `${rows.length} steps${failed ? ` · ${failed} failed` : ""}`;

  return (
    <Trace className="mt-2">
      <TraceCollapsible defaultOpen={Boolean(error) || failed > 0}>
        <TraceCollapsibleTrigger aria-label="Toggle tool trace">
          <TraceLine status={error || failed ? "error" : undefined}>
            <TraceIcon>
              <Wrench />
            </TraceIcon>
            <TraceTitle>{summary}</TraceTitle>
            {totalMs > 0 ? <TraceDescription>{totalMs} ms</TraceDescription> : null}
          </TraceLine>
        </TraceCollapsibleTrigger>
        <TraceCollapsibleContent>
          <Trace>
            {error ? (
              <TraceLine status="error">
                <TraceIcon>
                  <CircleAlertIcon />
                </TraceIcon>
                <TraceTitle>{explainReason(error).title}</TraceTitle>
                <TraceDescription>{error}</TraceDescription>
              </TraceLine>
            ) : null}
            {rows.map((row, idx) => {
              const steps = executedPipelineSteps(row);
              const line = (
                <TraceLine status={row.status === "ERROR" || row.status === "BLOCKED" ? "error" : undefined}>
                  <TraceIcon>{statusIcon(row.status)}</TraceIcon>
                  <TraceTitle>{toolLabel(row.tool)}</TraceTitle>
                  <TraceDescription className="flex items-center gap-1">
                    <span className="rounded border border-border px-1 text-[10px]">{row.status}</span>
                    {row.duration_ms != null ? (
                      <span className="inline-flex items-center gap-0.5">
                        <Clock3 className="size-3" aria-hidden />
                        {row.duration_ms} ms
                      </span>
                    ) : null}
                  </TraceDescription>
                </TraceLine>
              );
              if (steps.length === 0 && !row.error_code) {
                return <div key={`${row.tool}-${row.call_id ?? idx}`}>{line}</div>;
              }
              return (
                <TraceCollapsible key={`${row.tool}-${row.call_id ?? idx}`}>
                  <TraceCollapsibleTrigger aria-label={`Toggle ${toolLabel(row.tool)} details`}>{line}</TraceCollapsibleTrigger>
                  <TraceCollapsibleContent>
                    <Trace>
                      {row.error_code ? (
                        <TraceLine status="error">
                          <TraceIcon>
                            <CircleAlertIcon />
                          </TraceIcon>
                          <TraceTitle>{explainReason(row.error_code).title}</TraceTitle>
                          <TraceDescription>{row.error_code}</TraceDescription>
                        </TraceLine>
                      ) : null}
                      {steps.map((step) => (
                        <TraceLine key={step.id}>
                          <TraceIcon>
                            <CheckCircle2 className="size-3.5 text-profit" />
                          </TraceIcon>
                          <TraceTitle>{step.label}</TraceTitle>
                          {step.detail ? <TraceDescription>{step.detail}</TraceDescription> : null}
                        </TraceLine>
                      ))}
                    </Trace>
                  </TraceCollapsibleContent>
                </TraceCollapsible>
              );
            })}
          </Trace>
        </TraceCollapsibleContent>
      </TraceCollapsible>
    </Trace>
  );
}
