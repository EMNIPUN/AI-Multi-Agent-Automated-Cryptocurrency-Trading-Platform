"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

import { formatLocalAndUtc } from "../lib/time-formatters";
import type { ExplainMode, StudioProjection, WorkflowStage } from "../types";

export function DecisionInspector({
  projection,
  stage,
  explainMode,
}: {
  projection: StudioProjection;
  stage: WorkflowStage | null;
  explainMode: ExplainMode;
}) {
  const reduce = useReducedMotion();
  const candle = formatLocalAndUtc(projection.lastConfirmedCandleAt);

  return (
    <Card className="h-full border-[#253348] bg-[#101827]">
      <CardHeader>
        <CardTitle className="text-base">Why This Decision?</CardTitle>
        <CardDescription>
          Structured evidence only. Missing fields show as unavailable — never invented.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <AnimatePresence mode="wait">
          <motion.div
            key={`${projection.signalAction}-${stage?.id ?? "none"}-${explainMode}`}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="space-y-4"
          >
            <Section title="Market context">
              <Row label="Symbol" value={projection.symbol} />
              <Row label="Timeframe" value={`${projection.interval}m`} />
              <Row label="Confirmed candle" value={candle.utc} />
              <Row
                label="Freshness"
                value={projection.heartbeatStale ? "Stale / unknown" : "Heartbeat fresh"}
              />
              <Row label="Environment" value={projection.executionMode} />
            </Section>

            <Section title="Technical indicators">
              <Row
                label="EMA fast"
                value={projection.emaFast != null ? String(projection.emaFast) : "Evidence unavailable"}
              />
              <Row
                label="EMA slow"
                value={projection.emaSlow != null ? String(projection.emaSlow) : "Evidence unavailable"}
              />
              <Row
                label="RSI"
                value={projection.rsi != null ? String(projection.rsi) : "Evidence unavailable"}
              />
              {explainMode === "advanced" ? (
                <Row
                  label="Trend hint"
                  value={
                    projection.emaFast != null && projection.emaSlow != null
                      ? projection.emaFast > projection.emaSlow
                        ? "Fast above slow (observed values)"
                        : "Fast at/below slow (observed values)"
                      : "Evidence unavailable"
                  }
                />
              ) : null}
            </Section>

            <Section title="Strategy conditions">
              <Condition
                label="Confirmed candle requirement"
                result={projection.lastConfirmedCandleAt ? "PASS" : "UNKNOWN"}
              />
              <Condition
                label="Indicator snapshot present"
                result={
                  projection.emaFast != null && projection.rsi != null ? "PASS" : "NOT EVALUATED"
                }
              />
              <Condition
                label="Entry / exit rule detail"
                result="NOT EVALUATED"
                note="Per-rule PASS/FAIL bits are not exported by the worker yet."
              />
            </Section>

            <Section title="Signal">
              <div className="flex items-center gap-2">
                <Badge
                  variant={
                    projection.signalAction === "BUY"
                      ? "success"
                      : projection.signalAction === "SELL"
                        ? "danger"
                        : "secondary"
                  }
                >
                  {projection.signalAction ?? "unavailable"}
                </Badge>
              </div>
              <p className="mt-2 text-muted-foreground">
                {projection.signalReason || "Evidence unavailable"}
              </p>
              {projection.signalAction === "HOLD" ? (
                <p className="mt-2 text-xs text-muted-foreground">
                  HOLD means analysis completed without an actionable trade proposal. It is not a fill.
                </p>
              ) : null}
            </Section>

            <Section title="Risk review">
              <Badge
                variant={
                  projection.riskVerdict === "BLOCKED"
                    ? "danger"
                    : projection.riskVerdict === "APPROVED"
                      ? "success"
                      : "outline"
                }
              >
                {projection.riskVerdict}
              </Badge>
              <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                {(projection.riskReasons.length ? projection.riskReasons : ["Evidence unavailable"]).map(
                  (reason) => (
                    <li key={reason}>{reason}</li>
                  ),
                )}
              </ul>
            </Section>

            <Section title="Execution result">
              {projection.orders.length === 0 ? (
                <p className="text-muted-foreground">
                  No evidenced order intent in this snapshot. Risk approval alone is not placement.
                </p>
              ) : (
                projection.orders.slice(0, 4).map((order) => (
                  <div key={order.client_order_id} className="mb-2 rounded border border-[#253348] p-2">
                    <div className="flex justify-between gap-2">
                      <span className="font-mono text-xs">{order.client_order_id}</span>
                      <Badge variant="outline">{order.state}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      qty {order.qty ?? "—"} · filled {order.filled_qty ?? "—"}
                    </p>
                  </div>
                ))
              )}
            </Section>

            {stage ? (
              <>
                <Separator />
                <Section title={`Selected stage · ${stage.label}`}>
                  <Row label="State" value={stage.state} />
                  <Row label="Summary" value={stage.summary} />
                  {explainMode === "advanced" ? (
                    <Row
                      label="Event IDs"
                      value={stage.eventIds.slice(-3).join(", ") || "none"}
                    />
                  ) : null}
                </Section>
              </>
            ) : null}
          </motion.div>
        </AnimatePresence>
      </CardContent>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        {title}
      </h3>
      <div className="space-y-1.5">{children}</div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="max-w-[60%] text-right text-xs text-foreground">{value}</span>
    </div>
  );
}

function Condition({
  label,
  result,
  note,
}: {
  label: string;
  result: "PASS" | "FAIL" | "NOT EVALUATED" | "UNKNOWN";
  note?: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">{label}</span>
        <Badge
          variant={
            result === "PASS" ? "success" : result === "FAIL" ? "danger" : "outline"
          }
        >
          {result}
        </Badge>
      </div>
      {note ? <p className="mt-1 text-[10px] text-muted-foreground">{note}</p> : null}
    </div>
  );
}
