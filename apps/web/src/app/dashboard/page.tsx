"use client";

import { Activity, ShieldAlert } from "lucide-react";

import { WalletBalancePanel } from "@/components/WalletBalancePanel";
import { AnimatedList } from "@/components/magicui/animated-list";
import { BorderBeam } from "@/components/magicui/border-beam";
import { NumberTicker } from "@/components/magicui/number-ticker";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { MetricCard } from "@/components/shared/MetricCard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { dashboardFixture } from "@/lib/fixtures/dashboard";

export default function DashboardPage() {
  const f = dashboardFixture;
  return (
    <div>
      <PageHeader
        title="Command Dashboard"
        description="Operator overview for equity, agent health, risk, and activity. Live trading stays disabled."
      />
      <DataModeBanner mode={f.data_mode} notes={f.notes} />

      <div className="mb-4">
        <WalletBalancePanel />
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Paper equity (SAMPLE)"
          hint="Virtual funds — not Bybit"
          tone="profit"
          value={
            <>
              $<NumberTicker value={f.paper.equity} />
            </>
          }
        />
        <MetricCard label="Paper cash" value={f.paper.cash.toFixed(2)} />
        <MetricCard label="Unrealized" value={f.paper.unrealized.toFixed(2)} tone="profit" />
        <MetricCard label="Realized" value={f.paper.realized.toFixed(2)} tone="loss" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="relative overflow-hidden lg:col-span-1">
          <BorderBeam />
          <CardHeader>
            <CardTitle>Paper vs real</CardTitle>
            <CardDescription>Keep these balances visually separate</CardDescription>
          </CardHeader>
          <CardContent>
            <Badge variant="sample">PAPER ≠ REAL</Badge>
            <p className="mt-3 text-sm text-muted-foreground">
              The wallet card above is the live UNIFIED read when the API is up. These metrics
              stay labeled SAMPLE.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" /> Agent status
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <Badge variant="warning">{f.agent.status}</Badge>
              {f.agent.heartbeat_stale ? <Badge variant="danger">STALE</Badge> : null}
            </div>
            <p className="text-muted-foreground">
              {f.agent.strategy} · {f.agent.symbol} · {f.agent.interval}m
            </p>
            <p className="text-xs text-muted-foreground">
              Worker publisher not wired — no fabricated RUNNING animation.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-[hsl(var(--warning))]" /> Risk snapshot
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Badge variant="outline">Verdict: {f.risk.verdict}</Badge>
            <p>Daily loss limit concept: {f.risk.daily_loss_limit}</p>
            <ul className="list-disc pl-4 text-xs text-muted-foreground">
              {f.risk.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Activity timeline</CardTitle>
          <CardDescription>Explicit SAMPLE events — not live stream</CardDescription>
        </CardHeader>
        <CardContent>
          <AnimatedList>
            {f.activity.map((a) => (
              <div
                key={a.id}
                className="rounded-lg border border-border/70 bg-muted/30 px-3 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{a.title}</span>
                  <Badge variant="sample">{a.at}</Badge>
                </div>
                <p className="text-xs text-muted-foreground">{a.detail}</p>
              </div>
            ))}
          </AnimatedList>
        </CardContent>
      </Card>
    </div>
  );
}
