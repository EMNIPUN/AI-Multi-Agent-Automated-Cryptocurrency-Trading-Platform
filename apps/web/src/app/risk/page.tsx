"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { PageFrame, SectionPanel } from "@/components/command-center";
import { RiskIndicator, StatusBadge } from "@/components/design-system";
import { EmptyState } from "@/components/shared/EmptyState";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { Button } from "@/components/ui/button";

type RiskFeed = {
  halted?: boolean;
  halt_reason?: string | null;
  supervisor_state?: string;
  daily_loss_fraction?: string | null;
  drawdown_fraction?: string | null;
  daily_loss_limit_fraction?: string;
  drawdown_limit_fraction?: string;
  open_exposure_positions?: number;
  equity?: string | null;
  drawdown?: string | null;
  peak_equity?: string | null;
  label?: string;
  mode?: string;
};

export default function RiskPage() {
  const [risk, setRisk] = useState<RiskFeed | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/api/orchestrator/risk", { cache: "no-store" });
        const body = (await res.json().catch(() => ({}))) as RiskFeed & { detail?: string };
        if (!cancelled) {
          if (!res.ok) {
            setError(String(body.detail || "risk_unavailable"));
            setRisk(null);
          } else {
            setRisk(body);
            setError(null);
          }
        }
      } catch {
        if (!cancelled) {
          setError("api_unreachable");
          setRisk(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const halted = Boolean(risk?.halted);
  const state = halted ? "halted" : risk ? "ok" : "unknown";

  return (
    <PageFrame
      title="Risk Center"
      description="PAPER risk facts from the supervisor journal — daily loss, halt, exposure. LIVE stays locked."
      modes={["readonly", "paper", "live"]}
    >
      <DataModeBanner
        mode={risk ? "paper" : "unavailable"}
        notes={[risk?.label || "PAPER risk facts only — not exchange margin"]}
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <StatusBadge label="LIVE locked" tone="live" />
        <StatusBadge label="PAPER preferred" tone="paper" />
        <StatusBadge label={halted ? "HALTED" : String(risk?.supervisor_state || "—")} tone={halted ? "danger" : "neutral"} />
      </div>
      <SectionPanel
        title="Risk snapshot"
        description="Fail-closed: halt banners only appear from backend PAPER risk feed."
      >
        <RiskIndicator
          state={state as "ok" | "halted" | "unknown"}
          reason={
            error
              ? `Risk feed unavailable (${error}). Fail closed — live trading stays locked.`
              : halted
                ? `Paper risk halt: ${risk?.halt_reason || "blocked"}`
                : "Paper supervisor risk within configured limits."
          }
          className="mb-4"
        />
        {risk ? (
          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 text-sm">
            <div><dt className="text-xs text-muted-foreground">Equity</dt><dd className="font-mono">{risk.equity ?? "—"}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Drawdown</dt><dd className="font-mono">{risk.drawdown ?? "—"}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Peak equity</dt><dd className="font-mono">{risk.peak_equity ?? "—"}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Daily loss frac</dt><dd className="font-mono">{String(risk.daily_loss_fraction ?? "—")} / {risk.daily_loss_limit_fraction}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Drawdown frac</dt><dd className="font-mono">{String(risk.drawdown_fraction ?? "—")} / {risk.drawdown_limit_fraction}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Open positions</dt><dd className="font-mono">{risk.open_exposure_positions ?? 0}</dd></div>
          </dl>
        ) : (
          <EmptyState
            title="Risk snapshot unavailable"
            badge="Fail closed"
            description="Durable halt state remains on the trading engine, not in the browser."
            className="border-0 bg-transparent"
          />
        )}
        <Button asChild variant="outline" size="sm" className="mt-4 rounded-full">
          <Link href="/autonomy">Open Autonomous Trading</Link>
        </Button>
      </SectionPanel>
    </PageFrame>
  );
}
