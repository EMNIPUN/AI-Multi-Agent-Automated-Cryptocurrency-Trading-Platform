"use client";

import Link from "next/link";
import { AlertTriangle, Sparkles } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

import { AnimatedCircularProgressBar } from "@/components/magicui/animated-circular-progress-bar";
import { BorderBeam } from "@/components/magicui/border-beam";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Shimmer } from "@/components/ui/shimmer";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { formatAge } from "../lib/time-formatters";
import { studioSpring } from "../lib/motion-tokens";
import type { ExplainMode, StudioProjection, StudioViewMode } from "../types";

const VIEW_MODES: Array<{ id: StudioViewMode; label: string; hint: string }> = [
  { id: "live", label: "Live", hint: "Worker" },
  { id: "sample", label: "Demo", hint: "Safe sample" },
  { id: "replay", label: "Replay", hint: "History" },
];

function statusCopy(projection: StudioProjection) {
  if (projection.dataMode === "unavailable") {
    return {
      title: "Agent offline",
      body: "We can’t reach worker telemetry yet. Demo mode still works.",
    };
  }
  if (projection.agentStatus === "RUNNING" && !projection.heartbeatStale) {
    return {
      title: "Agent is watching",
      body: `Tracking ${projection.symbol} on ${projection.interval}m · ${projection.executionMode.replace(/_/g, " ").toLowerCase()}`,
    };
  }
  if (projection.agentStatus === "HALTED") {
    return {
      title: "Agent halted",
      body: "Risk or system halt — live actions stay blocked.",
    };
  }
  return {
    title: "Agent resting",
    body: projection.statusLabel || "Waiting for a fresh heartbeat from the worker.",
  };
}

function freshnessScore(projection: StudioProjection) {
  if (projection.evidenceFreshness === "fresh") return 92;
  if (projection.evidenceFreshness === "stale") return 38;
  return 8;
}

export function AgentStudioHeader({
  projection,
  viewMode,
  onViewMode,
  explainMode,
  onExplainMode,
}: {
  projection: StudioProjection;
  viewMode: StudioViewMode;
  onViewMode: (mode: StudioViewMode) => void;
  explainMode: ExplainMode;
  onExplainMode: (mode: ExplainMode) => void;
}) {
  const reduce = useReducedMotion();
  const copy = statusCopy(projection);
  const age = formatAge(projection.heartbeatAt);
  const score = freshnessScore(projection);

  return (
    <motion.header
      layout={!reduce}
      className="relative mb-5 overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] p-5 shadow-[var(--panel-shadow)] md:p-6"
    >
      <BorderBeam size={260} duration={14} colorFrom="#f59e0b" colorTo="#ffffff" />

      <div className="relative z-10 flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="badge-intro text-xs">
              <Sparkles className="h-3 w-3" />
                Live AI Analysis
            </span>
            <Badge variant="outline" className="rounded-full border-white/15 text-white/70">
              {projection.executionMode.replace(/_/g, " ")}
            </Badge>
            {projection.dataMode === "fixture" ? (
              <Badge variant="sample" className="rounded-full">
                Demo data
              </Badge>
            ) : null}
          </div>
          <h1 className="text-metallic text-2xl font-medium tracking-tight md:text-3xl">
            {copy.title}
          </h1>
          <p className="mt-1 max-w-xl text-sm text-white/55">{copy.body}</p>
          {projection.analyzing || projection.agentStatus === "RUNNING" ? (
            <Shimmer className="mt-2 text-xs">
              {projection.analyzing
                ? "Generating analysis…"
                : "Watching markets & streaming evidence…"}
            </Shimmer>
          ) : projection.heartbeatStale || projection.dataMode === "unavailable" ? (
            <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-amber-200/90">
              <AlertTriangle className="h-3.5 w-3.5" />
              Evidence may be incomplete · last beat {age}
            </p>
          ) : (
            <p className="mt-2 text-xs text-white/40">Heartbeat {age}</p>
          )}
        </div>

        <div className="flex items-center gap-4">
          <AnimatedCircularProgressBar
            value={score}
            gaugePrimaryColor="#f59e0b"
            gaugeSecondaryColor="rgba(255,255,255,0.12)"
            label="health"
            className="size-24"
          />
          <div className="hidden text-sm text-white/50 sm:block">
            <p className="font-medium text-white/80">{projection.symbol}</p>
            <p>{projection.interval}m timeframe</p>
            <p className="capitalize">{projection.evidenceFreshness} evidence</p>
          </div>
        </div>
      </div>

      <div className="relative z-10 mt-5 flex flex-wrap items-center gap-3">
        <Tabs
          value={viewMode}
          onValueChange={(value) => onViewMode(value as StudioViewMode)}
        >
          <TabsList aria-label="Data source" className="w-auto">
            {VIEW_MODES.map((mode) => (
              <TabsTrigger key={mode.id} value={mode.id}>
                {mode.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <Separator orientation="vertical" className="hidden h-8 bg-white/15 sm:block" />

        <Select value={explainMode} onValueChange={(v) => onExplainMode(v as ExplainMode)}>
          <SelectTrigger className="w-[150px] rounded-full border-white/15" aria-label="Detail level">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="simple">Simple view</SelectItem>
            <SelectItem value="advanced">Advanced view</SelectItem>
          </SelectContent>
        </Select>

        <Link
          href="/paper"
          className="rounded-full border border-white/15 px-3 py-1.5 text-xs text-white/70 transition hover:border-amber-400/40 hover:text-amber-100"
        >
          Paper journal (read-only)
        </Link>
        <Link
          href="/backtesting"
          className="rounded-full border border-white/15 px-3 py-1.5 text-xs text-white/70 transition hover:border-amber-400/40 hover:text-amber-100"
        >
          Backtesting
        </Link>
      </div>
    </motion.header>
  );
}
