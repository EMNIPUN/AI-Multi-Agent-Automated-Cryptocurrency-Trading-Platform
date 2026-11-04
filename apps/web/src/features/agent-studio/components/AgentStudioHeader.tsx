"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  Activity,
  AlertTriangle,
  CircleHelp,
  Pause,
  Radio,
} from "lucide-react";

import { CryptoNovaMark } from "@/components/brand/CryptoNovaLogo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

import { formatAge, formatLocalAndUtc } from "../lib/time-formatters";
import type { ExplainMode, StudioProjection, StudioViewMode } from "../types";

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
  const hb = formatLocalAndUtc(projection.heartbeatAt);
  const age = formatAge(projection.heartbeatAt);

  return (
    <header className="mb-4 space-y-3 rounded-xl border border-[#253348] bg-[#101827] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <CryptoNovaMark className="h-11 w-11" priority />
          <div>
            <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              CryptoNova
            </p>
            <h1 className="font-display text-2xl tracking-tight md:text-3xl">
              AI Agent Studio
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">{projection.statusLabel}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <AnimatePresence mode="wait">
            <motion.div
              key={projection.agentStatus}
              initial={reduce ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduce ? undefined : { opacity: 0 }}
              transition={{ duration: 0.18 }}
            >
              <Badge
                variant={
                  projection.agentStatus === "RUNNING"
                    ? "success"
                    : projection.agentStatus === "HALTED"
                      ? "danger"
                      : "warning"
                }
              >
                <Activity className="mr-1 h-3 w-3" />
                {projection.agentStatus}
              </Badge>
            </motion.div>
          </AnimatePresence>
          <Badge variant="outline">{projection.executionMode}</Badge>
          <Badge variant={projection.dataMode === "live" ? "success" : projection.dataMode === "fixture" ? "sample" : "warning"}>
            {projection.dataMode === "live" ? "LIVE WORKER" : projection.dataMode === "fixture" ? "SAMPLE" : "UNAVAILABLE"}
          </Badge>
          {viewMode === "replay" ? (
            <Badge variant="ai">
              <Pause className="mr-1 h-3 w-3" />
              REPLAY
            </Badge>
          ) : null}
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Meta label="Symbol / TF" value={`${projection.symbol} · ${projection.interval}m`} />
        <Meta
          label="Heartbeat"
          value={projection.heartbeatStale ? `STALE · ${age}` : `Fresh · ${age}`}
          hint={`Local ${hb.local} · UTC ${hb.utc}`}
        />
        <Meta
          label="Last confirmed candle"
          value={formatLocalAndUtc(projection.lastConfirmedCandleAt).utc}
        />
        <Meta
          label="Data source"
          value={viewMode === "sample" ? "Explicit SAMPLE" : viewMode === "replay" ? "Historical replay" : "Worker ledger"}
          icon={<Radio className="h-3.5 w-3.5" />}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Select value={viewMode} onValueChange={(v) => onViewMode(v as StudioViewMode)}>
          <SelectTrigger className="w-[180px]" aria-label="Studio view mode">
            <SelectValue placeholder="View mode" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="live">LIVE worker</SelectItem>
            <SelectItem value="sample">SAMPLE</SelectItem>
            <SelectItem value="replay">REPLAY</SelectItem>
          </SelectContent>
        </Select>
        <Select value={explainMode} onValueChange={(v) => onExplainMode(v as ExplainMode)}>
          <SelectTrigger className="w-[160px]" aria-label="Explainability mode">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="simple">Simple mode</SelectItem>
            <SelectItem value="advanced">Advanced mode</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="ghost" size="sm" className="gap-1 text-muted-foreground" asChild>
          <a href="#how-to-read">
            <CircleHelp className="h-4 w-4" />
            How to read this
          </a>
        </Button>
        {projection.heartbeatStale || projection.dataMode === "unavailable" ? (
          <span className="inline-flex items-center gap-1 text-xs text-[hsl(var(--warning))]">
            <AlertTriangle className="h-3.5 w-3.5" />
            Evidence may be incomplete
          </span>
        ) : null}
      </div>
    </header>
  );
}

function Meta({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: string;
  hint?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className={cn("rounded-lg border border-[#253348]/80 bg-[#080D19]/50 px-3 py-2")}>
      <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <p className="mt-1 flex items-center gap-1.5 font-mono text-xs text-foreground">
        {icon}
        {value}
      </p>
      {hint ? <p className="mt-1 text-[10px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
