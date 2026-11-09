"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  Bot,
  CandlestickChart,
  FlaskConical,
  ShieldCheck,
  Sparkles,
  Wallet,
} from "lucide-react";

import {
  AgentStatusList,
  MetricGrid,
  MetricTile,
  ModeBadge,
  PageFrame,
  SectionPanel,
} from "@/components/command-center";
import { BlurFade } from "@/components/magicui/blur-fade";
import { NumberTicker } from "@/components/magicui/number-ticker";
import { Ripple } from "@/components/magicui/ripple";
import { NewsAlertStrip } from "@/components/news/NewsAlertStrip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { agentsForStatusList } from "@/lib/agents/registry";
import { cn } from "@/lib/utils";

type AnyRow = Record<string, unknown>;

async function readJson(path: string) {
  try {
    const res = await fetch(path, { cache: "no-store" });
    const body = (await res.json().catch(() => ({}))) as AnyRow;
    return { ok: res.ok, body };
  } catch {
    return { ok: false, body: {} as AnyRow };
  }
}

const QUICK_LINKS = [
  {
    href: "/autonomy",
    title: "Autonomous Trading",
    detail: "Session controls, decisions & exits",
    icon: ShieldCheck,
  },
  {
    href: "/orchestrator",
    title: "Orchestrator",
    detail: "Primary AI supervision chat",
    icon: Bot,
  },
  {
    href: "/agents/live",
    title: "Live AI Analysis",
    detail: "Multi-agent studio & signals",
    icon: Activity,
  },
  {
    href: "/markets",
    title: "Markets",
    detail: "Public charts & tickers",
    icon: CandlestickChart,
  },
  {
    href: "/paper",
    title: "Paper Trading",
    detail: "Simulated journal only",
    icon: FlaskConical,
  },
  {
    href: "/portfolio",
    title: "Portfolio",
    detail: "Read-only wallet snapshot",
    icon: Wallet,
  },
  {
    href: "/risk",
    title: "Risk Management",
    detail: "Guards stay paper-scoped",
    icon: ShieldCheck,
  },
];

export function DashboardHome() {
  const [loading, setLoading] = useState(true);
  const [orch, setOrch] = useState<AnyRow | null>(null);
  const [report, setReport] = useState<AnyRow | null>(null);
  const [paper, setPaper] = useState<AnyRow | null>(null);
  const [wallet, setWallet] = useState<AnyRow | null>(null);
  const [autonomy, setAutonomy] = useState<AnyRow | null>(null);
  const [runtime, setRuntime] = useState<AnyRow | null>(null);
  const [risk, setRisk] = useState<AnyRow | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [st, rp, pap, wal, auto, agentsRt, riskFeed] = await Promise.all([
        readJson("/api/orchestrator/status"),
        readJson("/api/orchestrator/report"),
        readJson("/api/paper/status"),
        readJson("/api/exchange/wallet"),
        readJson("/api/orchestrator/autonomy"),
        readJson("/api/orchestrator/agents/runtime"),
        readJson("/api/orchestrator/risk"),
      ]);
      if (cancelled) return;
      setOrch(st.ok ? st.body : null);
      setReport(rp.ok ? rp.body : null);
      setPaper(pap.ok ? pap.body : null);
      setWallet(wal.ok ? wal.body : null);
      setAutonomy(auto.ok ? auto.body : null);
      setRuntime(agentsRt.ok ? agentsRt.body : null);
      setRisk(riskFeed.ok ? riskFeed.body : null);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const session = (autonomy?.session as AnyRow | undefined) || null;
  const supervisor = String(session?.state || orch?.state || "STOPPED").toUpperCase();
  const journal = (autonomy?.journal as AnyRow | undefined) || null;
  const openPositions =
    Number(report?.open_positions ?? (autonomy?.open_position ? 1 : 0) ?? orch?.open_positions ?? 0) || 0;
  const equityRaw = journal?.equity ?? report?.equity;
  const equityNum =
    equityRaw == null || equityRaw === "" || equityRaw === "—"
      ? null
      : Number(equityRaw);
  const paperEnabled = Boolean(paper?.paper_read_api_enabled);
  const walletEquity = wallet?.total_equity != null ? Number(wallet.total_equity) : null;
  const strategyVersion = String(autonomy?.strategy_version || runtime?.strategy_version || "—");
  const halted = Boolean(risk?.halted);
  const agents = agentsForStatusList(
    Array.isArray(runtime?.agents)
      ? (runtime?.agents as { agent_id: string; label: string; status: string }[])
      : null,
  );

  return (
    <PageFrame
      title="Overview"
      description="Fleet overview for the advanced multi-agent control plane. Primary ops live on Autonomous Trading; LIVE stays locked."
      modes={["readonly", "paper", "live"]}
      actions={
        <Button asChild className="rounded-full" variant="secondary">
          <Link href="/autonomy">
            Open Autonomous Trading
            <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
          </Link>
        </Button>
      }
    >
      <NewsAlertStrip />

      <BlurFade>
        <section className="relative overflow-hidden rounded-3xl border border-border bg-gradient-to-b from-zinc-950 via-black to-black px-5 py-7 md:px-8">
          <Ripple className="opacity-20" mainCircleSize={80} numCircles={4} />
          <div className="relative z-10 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-[11px] uppercase tracking-[0.16em] text-brand">
                AI Trading Command Center
              </p>
              <h2 className="mt-2 text-2xl font-medium tracking-tight text-foreground md:text-3xl">
                Calibrated agents. Autonomous paper. Testnet gated.
              </h2>
              <p className="mt-2 text-sm text-foreground">
                Strategy {strategyVersion}. Scores are historical agreement, not guaranteed edge.
                LLM/news stay advisory. Nothing here places a live exchange order.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <ModeBadge mode="paper" />
              <ModeBadge mode="live" />
              <Badge variant="outline" className="rounded-full">
                Supervisor {supervisor}
              </Badge>
              {halted ? (
                <Badge variant="destructive" className="rounded-full">
                  Risk halt
                </Badge>
              ) : null}
            </div>
          </div>
        </section>
      </BlurFade>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner className="size-4" />
          Loading command metrics…
        </div>
      ) : (
        <MetricGrid>
          <MetricTile label="Supervisor" hint="Orchestrator feature gate" accent>
            <span className="font-mono text-base">
              {supervisor}
              <span className="text-foreground"> · </span>
              {orch?.enabled ? "on" : "off"}
            </span>
          </MetricTile>
          <MetricTile label="Execution mode" hint="TESTNET gated · LIVE locked">
            <span className="font-mono text-base">PAPER · TESTNET gated · LIVE locked</span>
          </MetricTile>
          <MetricTile label="Strategy" hint="Calibrated historical agreement only">
            <span className="font-mono text-base">{strategyVersion}</span>
          </MetricTile>
          <MetricTile label="Paper equity" hint="Journal report only">
            {equityNum != null && Number.isFinite(equityNum) ? (
              <span className="font-mono">
                <NumberTicker value={equityNum} decimalPlaces={2} />{" "}
                <span className="text-sm text-foreground">
                  {String(report?.currency || "USDT")}
                </span>
              </span>
            ) : (
              <span className="font-mono text-foreground">—</span>
            )}
          </MetricTile>
          <MetricTile label="Open positions" hint="Paper exposure">
            <span className="font-mono">
              <NumberTicker value={openPositions} />
            </span>
          </MetricTile>
        </MetricGrid>
      )}

      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <SectionPanel
          title="Desk readiness"
          description="Honest status from available read adapters — never invented balances."
          beam
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-border bg-muted/50 p-4">
              <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                Paper journal
              </p>
              <p className="mt-2 font-mono text-sm text-foreground">
                {paperEnabled ? "Read API enabled" : "Read API off / unavailable"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Sessions: {String(paper?.session_count ?? "—")}
              </p>
            </div>
            <div className="rounded-xl border border-border bg-muted/50 p-4">
              <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                Exchange wallet
              </p>
              <p className="mt-2 font-mono text-sm text-foreground">
                {walletEquity != null && Number.isFinite(walletEquity)
                  ? `${walletEquity.toLocaleString(undefined, { maximumFractionDigits: 2 })} equity`
                  : "Not connected / gated"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">Read-only UNIFIED when enabled</p>
            </div>
            <div className="rounded-xl border border-border bg-muted/50 p-4 sm:col-span-2">
              <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                Risk posture
              </p>
              <p className="mt-2 text-sm text-foreground">
                {halted
                  ? `Paper risk halt: ${String(risk?.halt_reason || "blocked")}`
                  : "Live trading disabled. Paper risk facts come from the supervisor journal."}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button asChild variant="outline" size="sm" className="rounded-full">
                  <Link href="/risk">Open Risk Center</Link>
                </Button>
                <Button asChild variant="secondary" size="sm" className="rounded-full">
                  <Link href="/autonomy">Ops desk</Link>
                </Button>
              </div>
            </div>
          </div>
        </SectionPanel>

        <SectionPanel
          title="Agent fleet"
          description="Per-agent status from latest decision contributions — not a cloned supervisor heartbeat."
        >
          <AgentStatusList agents={agents} />
        </SectionPanel>
      </div>

      <SectionPanel
        title="Jump to workspace"
        description="Agent-first tools first, then trading desk and research."
      >
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {QUICK_LINKS.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "group rounded-2xl border border-border bg-muted/30 p-4 transition-colors hover:border-border hover:bg-muted/40",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-muted/70">
                    <Icon className="h-4 w-4 text-brand" />
                  </div>
                  <ArrowRight className="h-4 w-4 text-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
                </div>
                <p className="mt-3 text-sm font-medium text-foreground">{item.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">{item.detail}</p>
              </Link>
            );
          })}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button asChild variant="ghost" size="sm" className="rounded-full">
            <Link href="/llm">
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              LLM Intelligence
            </Link>
          </Button>
          <Button asChild variant="ghost" size="sm" className="rounded-full">
            <Link href="/system">System Health</Link>
          </Button>
        </div>
      </SectionPanel>
    </PageFrame>
  );
}
