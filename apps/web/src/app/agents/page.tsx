import Link from "next/link";

import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const AGENTS = [
  {
    name: "Market Data Agent",
    status: "Implemented",
    detail: "Confirmed public candles, spot/perp isolation, stale rejection",
    href: "/agents/live",
    ready: true,
  },
  {
    name: "Trend Agent",
    status: "Implemented",
    detail: "EMA20/50/200 alignment and crossover state — BULLISH/BEARISH/NEUTRAL",
    href: "/agents/live",
    ready: true,
  },
  {
    name: "Momentum Agent",
    status: "Implemented",
    detail: "RSI14 + momentum/volume context — never OB/OS alone as BUY/SELL",
    href: "/agents/live",
    ready: true,
  },
  {
    name: "Risk Agent",
    status: "Implemented",
    detail: "Paper-capital sizing, veto, cooldown, daily halt — no live balances",
    href: "/agents/live",
    ready: true,
  },
  {
    name: "Decision Coordinator",
    status: "Implemented",
    detail: "BUY/SELL/HOLD/BLOCKED with explainable score — signals only",
    href: "/agents/live",
    ready: true,
  },
  {
    name: "EMA/RSI Runner",
    status: "Implemented",
    detail: "Legacy single-strategy AgentRunner (still dry-run by default)",
    href: "/agents/live",
    ready: true,
  },
  {
    name: "SMC Agent",
    status: "Coming Soon",
    detail: "Smart-money concepts package not implemented",
    href: null,
    ready: false,
  },
];

export default function AgentsPage() {
  return (
    <div>
      <PageHeader
        title="Agents"
        description="Phase 4A multi-agent signals foundation. No real order submission."
      />
      <DataModeBanner
        mode="demo"
        notes={[
          "Signals are not executed trades",
          "Risk Agent veto cannot be overridden",
          "AGENT_ALLOW_LIVE stays false",
        ]}
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {AGENTS.map((a) => (
          <Card key={a.name}>
            <CardHeader>
              <CardTitle className="text-base">{a.name}</CardTitle>
              <CardDescription>{a.detail}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Badge variant={a.ready ? "success" : "secondary"}>{a.status}</Badge>
              {a.href ? (
                <Button asChild size="sm">
                  <Link href={a.href}>Open Agent Studio</Link>
                </Button>
              ) : (
                <Button size="sm" disabled>
                  Coming soon
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
