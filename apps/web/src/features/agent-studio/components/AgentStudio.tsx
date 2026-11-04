"use client";

import { useEffect, useMemo, useState } from "react";
import { BlurFade } from "@/components/magicui/blur-fade";
import { CandleChart } from "@/components/CandleChart";
import { LogoLoader } from "@/components/brand/LogoLoader";
import { WalletBalancePanel } from "@/components/WalletBalancePanel";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { useAgentSnapshot } from "../hooks/use-agent-snapshot";
import { useReplayState } from "../hooks/use-replay-state";
import { projectStudio } from "../lib/workflow-projector";
import type { ExplainMode, StudioViewMode } from "../types";
import { AgentStudioHeader } from "./AgentStudioHeader";
import { DecisionInspector } from "./DecisionInspector";
import { EventTimelinePanel } from "./EventTimelinePanel";
import { ReplayControls } from "./ReplayControls";
import { StudioWorkflow } from "./StudioWorkflow";

const EVENT_TO_STAGE: Record<string, string> = {
  "agent.heartbeat": "market",
  "market.candle_confirmed": "candle",
  "analysis.completed": "analysis",
  "signal.generated": "signal",
  "risk.approved": "risk",
  "risk.blocked": "risk",
  "risk.halted": "risk",
  "agent.halted": "risk",
  "order.intent_created": "intent",
  "order.accepted": "execution",
  "order.partially_filled": "reconcile",
  "order.filled": "position",
  "order.canceled": "reconcile",
  "order.reconciliation_required": "reconcile",
};

export function AgentStudio() {
  const [viewMode, setViewMode] = useState<StudioViewMode>("live");
  const [explainMode, setExplainMode] = useState<ExplainMode>("simple");
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [mobileTab, setMobileTab] = useState("overview");

  const { snap, loading } = useAgentSnapshot(viewMode === "replay" ? "live" : viewMode);
  const replayBase = snap;
  const replay = useReplayState(replayBase, viewMode === "replay");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("cryptonova.agentStudio.explainMode");
      if (saved === "simple" || saved === "advanced") setExplainMode(saved);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem("cryptonova.agentStudio.explainMode", explainMode);
    } catch {
      // ignore
    }
  }, [explainMode]);

  const projection = useMemo(() => {
    if (viewMode === "replay") return replay.projection;
    return snap ? projectStudio(snap) : null;
  }, [viewMode, replay.projection, snap]);

  if (loading && !projection) {
    return <LogoLoader fullScreen label="Loading AI Agent Studio…" />;
  }
  if (!projection) {
    return <LogoLoader fullScreen label="Waiting for agent evidence…" />;
  }

  const selectedStage =
    projection.stages.find((stage: { id: string }) => stage.id === selectedStageId) ?? null;
  const sample = projection.dataMode === "fixture";

  const workspace = (
    <>
      <div className="mb-4 grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.9fr)]">
        <StudioWorkflow
          stages={projection.stages}
          selectedId={selectedStageId}
          onSelect={(id) => setSelectedStageId(id || null)}
          demo={sample}
        />
        <DecisionInspector
          projection={projection}
          stage={selectedStage}
          explainMode={explainMode}
        />
      </div>

      <div className="mb-4 grid gap-4 xl:grid-cols-2">
        <Card className="border-[#253348] bg-[#101827]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              Market chart
              {sample ? <Badge variant="sample">SAMPLE</Badge> : null}
            </CardTitle>
            <CardDescription>
              EMA {projection.emaFast ?? "—"} / {projection.emaSlow ?? "—"} · RSI{" "}
              {projection.rsi ?? "—"}
              {projection.snapshot.candles.length === 0
                ? " · Candle series unavailable in this snapshot"
                : null}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CandleChart
              candles={projection.snapshot.candles}
              markers={projection.snapshot.markers}
              sample={sample}
            />
          </CardContent>
        </Card>

        <Card className="border-[#253348] bg-[#101827]">
          <CardHeader>
            <CardTitle className="text-base">Order lifecycle</CardTitle>
            <CardDescription>
              ACCEPTED ≠ FILLED. Missing stages stay unavailable until evidenced.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {projection.orders.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No evidenced intents in this view.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Client ID</TableHead>
                    <TableHead>State</TableHead>
                    <TableHead>Qty</TableHead>
                    <TableHead>Filled</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {projection.orders.map((order: (typeof projection.orders)[number]) => (
                    <TableRow key={order.client_order_id}>
                      <TableCell className="font-mono text-xs">
                        {order.client_order_id}
                        {order.sample ? " · SAMPLE" : ""}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{order.state}</Badge>
                      </TableCell>
                      <TableCell>{order.qty ?? "—"}</TableCell>
                      <TableCell>{order.filled_qty ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <EventTimelinePanel
        events={projection.events}
        selectedEventId={selectedEventId}
        onSelect={setSelectedEventId}
        onJumpStage={(eventType) => {
          const stageId = EVENT_TO_STAGE[eventType];
          if (stageId) setSelectedStageId(stageId);
        }}
      />
    </>
  );

  return (
    <BlurFade>
      <AgentStudioHeader
        projection={projection}
        viewMode={viewMode}
        onViewMode={(mode) => {
          setViewMode(mode);
          setSelectedEventId(null);
        }}
        explainMode={explainMode}
        onExplainMode={setExplainMode}
      />

      <ReplayControls
        enabled={viewMode === "replay"}
        playing={replay.playing}
        index={replay.index}
        total={replay.events.length}
        speed={replay.speed}
        gap={replay.gap}
        onPlay={() => replay.setPlaying(true)}
        onPause={() => replay.setPlaying(false)}
        onPrev={() => replay.setIndex(Math.max(0, replay.index - 1))}
        onNext={() =>
          replay.setIndex(Math.min(replay.events.length - 1, replay.index + 1))
        }
        onSpeed={replay.setSpeed}
        onScrub={replay.setIndex}
        onExit={() => setViewMode("live")}
      />

      <div className="mb-4">
        <WalletBalancePanel />
      </div>

      <div className="hidden lg:block">{workspace}</div>

      <div className="lg:hidden">
        <Tabs value={mobileTab} onValueChange={setMobileTab}>
          <TabsList className="mb-3 grid w-full grid-cols-5">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="workflow">Flow</TabsTrigger>
            <TabsTrigger value="chart">Chart</TabsTrigger>
            <TabsTrigger value="events">Events</TabsTrigger>
            <TabsTrigger value="decisions">Why</TabsTrigger>
          </TabsList>
          <TabsContent value="overview" className="space-y-3">
            <p className="text-sm text-muted-foreground">{projection.statusLabel}</p>
            <DecisionInspector
              projection={projection}
              stage={selectedStage}
              explainMode="simple"
            />
          </TabsContent>
          <TabsContent value="workflow">
            <StudioWorkflow
              stages={projection.stages}
              selectedId={selectedStageId}
              onSelect={(id) => setSelectedStageId(id || null)}
              demo={sample}
            />
          </TabsContent>
          <TabsContent value="chart">
            <CandleChart
              candles={projection.snapshot.candles}
              markers={projection.snapshot.markers}
              sample={sample}
            />
          </TabsContent>
          <TabsContent value="events">
            <EventTimelinePanel
              events={projection.events}
              selectedEventId={selectedEventId}
              onSelect={setSelectedEventId}
              onJumpStage={(eventType) => {
                const stageId = EVENT_TO_STAGE[eventType];
                if (stageId) setSelectedStageId(stageId);
              }}
            />
          </TabsContent>
          <TabsContent value="decisions">
            <DecisionInspector
              projection={projection}
              stage={selectedStage}
              explainMode={explainMode}
            />
          </TabsContent>
        </Tabs>
      </div>

      <section
        id="how-to-read"
        className="mt-6 rounded-xl border border-[#253348] bg-[#101827] p-4 text-sm text-muted-foreground"
      >
        <h2 className="mb-2 font-display text-base text-foreground">How to read this workflow</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>RUNNING means a fresh worker heartbeat — not that a trade is open.</li>
          <li>HOLD is an analysis result, not an order.</li>
          <li>Nodes light only from evidenced events. Empty stages stay IDLE or UNAVAILABLE.</li>
          <li>SAMPLE and LIVE worker views are never mixed.</li>
          <li>REPLAY reconstructs history locally and cannot place orders.</li>
        </ul>
      </section>
    </BlurFade>
  );
}
