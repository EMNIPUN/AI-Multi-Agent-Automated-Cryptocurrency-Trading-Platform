"use client";

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { CandleChart } from "@/components/CandleChart";
import { LogoLoader } from "@/components/brand/LogoLoader";
import { WalletBalancePanel } from "@/components/WalletBalancePanel";
import { BlurFade } from "@/components/magicui/blur-fade";
import { InteractiveHoverButton } from "@/components/magicui/interactive-hover-button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { useAgentSnapshot } from "../hooks/use-agent-snapshot";
import { useReplayState } from "../hooks/use-replay-state";
import { studioSpring } from "../lib/motion-tokens";
import { chartTimeForEvent, projectStudio } from "../lib/workflow-projector";
import type { ExplainMode, StudioViewMode } from "../types";
import { AgentLiveFeed } from "./AgentLiveFeed";
import { AgentStudioHeader } from "./AgentStudioHeader";
import { AgentWorkflowLive } from "./AgentWorkflowLive";
import { AutomationControlPanel } from "./AutomationControlPanel";
import { DecisionInspector } from "./DecisionInspector";
import { EventTimelinePanel } from "./EventTimelinePanel";
import { ReplayControls } from "./ReplayControls";
import { SignalsPanel } from "./SignalsPanel";
import { StudioAtmosphere, StudioReveal } from "./StudioMotion";
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

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "workflow", label: "Workflow" },
  { id: "chart", label: "Chart" },
  { id: "events", label: "Events" },
  { id: "wallet", label: "Wallet" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function AgentStudio() {
  const [viewMode, setViewMode] = useState<StudioViewMode>("live");
  const [explainMode, setExplainMode] = useState<ExplainMode>("simple");
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [chartFocusTime, setChartFocusTime] = useState<number | null>(null);
  const [tab, setTab] = useState<TabId>("overview");

  const reduce = useReducedMotion();
  const { snap, loading, error } = useAgentSnapshot(viewMode === "replay" ? "live" : viewMode);
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
    return (
      <div className="space-y-4 py-6" role="status" aria-label="Loading AI Agent Studio">
        <Skeleton className="h-40 w-full rounded-3xl" />
        <Skeleton className="h-10 w-full rounded-full" />
        <div className="grid gap-4 xl:grid-cols-2">
          <Skeleton className="h-72 rounded-3xl" />
          <Skeleton className="h-72 rounded-3xl" />
        </div>
        <LogoLoader label="Loading AI Agent Studio…" className="py-2" />
      </div>
    );
  }
  if (!projection) {
    return (
      <div
        className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-center"
        role="status"
        aria-live="polite"
      >
        <LogoLoader label="Waiting for agent evidence…" />
        {error ? (
          <p className="max-w-md text-sm text-muted-foreground">
            Worker telemetry unavailable. Switch to Demo to explore safely — Live never invents data.
          </p>
        ) : null}
        <InteractiveHoverButton
          onClick={() => {
            setViewMode("sample");
          }}
        >
          Open demo view
        </InteractiveHoverButton>
      </div>
    );
  }

  const selectedStage =
    projection.stages.find((stage: { id: string }) => stage.id === selectedStageId) ?? null;
  const sample = projection.dataMode === "fixture";
  const focusTime = chartFocusTime ?? projection.chartFocusTime;
  const candleTimes = new Set(projection.snapshot.candles.map((c) => c.time));

  const jumpEventToChart = (eventId: string) => {
    const event = projection.events.find((item) => item.event_id === eventId) ?? null;
    const time = chartTimeForEvent(event, candleTimes);
    setChartFocusTime(time);
    setSelectedEventId(eventId);
    const stageId = event ? EVENT_TO_STAGE[event.event_type] : null;
    if (stageId) setSelectedStageId(stageId);
    setTab("chart");
  };

  return (
    <div className="relative isolate min-h-[70vh] pb-8">
      <StudioAtmosphere />
      <StudioReveal>
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
      </StudioReveal>

      <AnimatePresence>
        {viewMode === "replay" ? (
          <motion.div
            key="replay"
            initial={reduce ? false : { opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -6 }}
            transition={studioSpring}
            className="mb-4"
          >
            <ReplayControls
              enabled
              playing={replay.playing}
              index={replay.index}
              total={replay.events.length}
              speed={replay.speed}
              gap={replay.gap}
              gapCount={replay.gapCount}
              largestGapMs={replay.largestGapMs}
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
          </motion.div>
        ) : null}
      </AnimatePresence>

      <Tabs
        value={tab}
        onValueChange={(value) => setTab(value as TabId)}
        className="mb-5 min-h-[32rem]"
      >
        <TabsList aria-label="Agent studio sections">
          {TABS.map((item) => (
            <TabsTrigger key={item.id} value={item.id}>
              {item.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <BlurFade className="space-y-4">
            <AutomationControlPanel />
            <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
              <AgentWorkflowLive
                stages={projection.stages}
                selectedId={selectedStageId}
                onSelect={(id) => setSelectedStageId(id)}
              />
              <AgentLiveFeed
                events={projection.events}
                selectedEventId={selectedEventId}
                onSelect={(id) => {
                  setSelectedEventId(id);
                  const event = projection.events.find((e) => e.event_id === id);
                  const stageId = event ? EVENT_TO_STAGE[event.event_type] : null;
                  if (stageId) setSelectedStageId(stageId);
                }}
              />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <DecisionInspector
                projection={projection}
                stage={selectedStage}
                explainMode={explainMode}
              />
              <SignalsPanel
                symbol={projection.symbol || "BTCUSDT"}
                category="linear"
                interval={projection.interval || "15"}
              />
            </div>
          </BlurFade>
        </TabsContent>

        <TabsContent value="workflow" className="mt-4 space-y-4">
          <BlurFade className="space-y-4">
            <AgentWorkflowLive
              stages={projection.stages}
              selectedId={selectedStageId}
              onSelect={(id) => setSelectedStageId(id)}
            />
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
          </BlurFade>
        </TabsContent>

        <TabsContent value="chart" className="mt-4">
          <BlurFade className="grid gap-4 xl:grid-cols-2">
            <Card className="overflow-hidden border-border bg-muted/40">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  Market chart
                  {sample ? <Badge variant="sample">SAMPLE</Badge> : null}
                  {projection.evidenceFreshness !== "fresh" ? (
                    <Badge variant="warning">{projection.evidenceFreshness}</Badge>
                  ) : null}
                </CardTitle>
                <CardDescription>
                  EMA {projection.emaFast ?? "—"} / {projection.emaSlow ?? "—"} · RSI{" "}
                  {projection.rsi ?? "—"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <CandleChart
                  candles={projection.snapshot.candles}
                  markers={projection.snapshot.markers}
                  sample={sample}
                  focusTime={focusTime}
                />
              </CardContent>
            </Card>

            <Card className="border-border bg-muted/40">
              <CardHeader>
                <CardTitle className="text-base">Order lifecycle</CardTitle>
                <CardDescription>
                  Accepted is not filled. Empty means no evidenced orders yet.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {projection.orders.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No evidenced intents in this view.</p>
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
          </BlurFade>
        </TabsContent>

        <TabsContent value="events" className="mt-4">
          <BlurFade className="grid gap-4 xl:grid-cols-2">
            <AgentLiveFeed
              events={projection.events}
              selectedEventId={selectedEventId}
              onSelect={setSelectedEventId}
            />
            <EventTimelinePanel
              events={projection.events}
              selectedEventId={selectedEventId}
              onSelect={setSelectedEventId}
              onJumpStage={(eventType) => {
                const stageId = EVENT_TO_STAGE[eventType];
                if (stageId) {
                  setSelectedStageId(stageId);
                  setTab("workflow");
                }
              }}
              onJumpChart={jumpEventToChart}
              candleTimes={candleTimes}
            />
          </BlurFade>
        </TabsContent>

        <TabsContent value="wallet" className="mt-4">
          <BlurFade>
            <WalletBalancePanel />
          </BlurFade>
        </TabsContent>
      </Tabs>

      <StudioReveal delay={0.08}>
        <section className="mt-6 rounded-2xl border border-border bg-muted/30 p-4 text-sm text-foreground">
          <h2 className="mb-2 text-base font-medium text-foreground">Quick tips</h2>
          <ul className="list-disc space-y-1 pl-5">
            <li>Live means a real worker heartbeat — not that a trade is open.</li>
            <li>Demo never mixes with live worker evidence.</li>
            <li>Replay only reconstructs history locally and cannot place orders.</li>
          </ul>
        </section>
      </StudioReveal>
    </div>
  );
}
