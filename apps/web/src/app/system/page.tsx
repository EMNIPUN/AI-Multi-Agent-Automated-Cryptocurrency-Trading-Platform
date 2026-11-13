"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";

import {
  MetricGrid,
  MetricTile,
  SectionPanel,
} from "@/components/command-center";
import { OverviewTemplate } from "@/components/design-system/templates";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

type AnyRow = Record<string, unknown>;

type Probe = {
  id: string;
  label: string;
  href?: string;
  ok: boolean | null;
  detail: string;
};

async function probe(path: string): Promise<{ ok: boolean; body: AnyRow; status: number }> {
  try {
    const res = await fetch(path, { cache: "no-store" });
    const body = (await res.json().catch(() => ({}))) as AnyRow;
    return { ok: res.ok, body, status: res.status };
  } catch {
    return { ok: false, body: {}, status: 0 };
  }
}

function summarize(
  id: string,
  label: string,
  href: string | undefined,
  result: { ok: boolean; body: AnyRow; status: number },
  enabledKey?: string,
): Probe {
  if (!result.ok) {
    return {
      id,
      label,
      href,
      ok: false,
      detail: result.status === 0 ? "unreachable" : `http_${result.status}`,
    };
  }
  if (enabledKey && result.body[enabledKey] === false) {
    return { id, label, href, ok: true, detail: "reachable · feature off" };
  }
  if (enabledKey && result.body[enabledKey] === true) {
    return { id, label, href, ok: true, detail: "reachable · enabled" };
  }
  return { id, label, href, ok: true, detail: "reachable" };
}

export default function SystemHealthPage() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [probes, setProbes] = useState<Probe[]>([]);

  async function load(soft = false) {
    if (soft) setRefreshing(true);
    else setLoading(true);
    const [orch, paper, backtest, news, llm, wallet] = await Promise.all([
      probe("/api/orchestrator/status"),
      probe("/api/paper/status"),
      probe("/api/backtests/status"),
      probe("/api/news/status"),
      probe("/api/llm/status"),
      probe("/api/exchange/wallet"),
    ]);
    setProbes([
      summarize("orch", "Orchestrator", "/orchestrator", orch, "enabled"),
      summarize("paper", "Paper journal", "/paper", paper, "paper_read_api_enabled"),
      summarize("backtest", "Backtests", "/backtesting", backtest, "enabled"),
      summarize("news", "News intelligence", "/news", news),
      summarize("llm", "LLM intelligence", "/llm", llm),
      summarize(
        "wallet",
        "Exchange wallet",
        "/portfolio",
        wallet.status === 401 || wallet.status === 403
          ? { ...wallet, ok: true }
          : wallet,
      ),
    ].map((p) => {
      if (p.id === "wallet" && (wallet.status === 401 || wallet.status === 403)) {
        return { ...p, ok: true, detail: "gated / not connected" };
      }
      return p;
    }));
    setLoading(false);
    setRefreshing(false);
  }

  useEffect(() => {
    void load();
  }, []);

  const healthy = probes.filter((p) => p.ok).length;
  const total = probes.length;

  return (
    <OverviewTemplate
      title="System Health"
      description="Read-only aggregate of local loopback adapters. No schema changes and no live trading unlock."
      modes={["readonly"]}
      actions={
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="rounded-full"
          disabled={refreshing || loading}
          onClick={() => void load(true)}
        >
          {refreshing || loading ? (
            <Spinner className="mr-1" data-icon="inline-start" />
          ) : (
            <RefreshCw className="mr-1 h-3.5 w-3.5" />
          )}
          Refresh
        </Button>
      }
    >
      <MetricGrid>
        <MetricTile label="Adapters checked" accent>
          <span className="font-mono">
            {loading ? "—" : `${healthy}/${total || "—"}`}
          </span>
        </MetricTile>
        <MetricTile label="Live trading" hint="Hard lock">
          <span className="font-mono text-base">OFF</span>
        </MetricTile>
        <MetricTile label="Execution mode" hint="Paper supervision only">
          <span className="font-mono text-base">PAPER</span>
        </MetricTile>
        <MetricTile label="Client secrets" hint="Keys stay on server">
          <span className="font-mono text-base">none in bundle</span>
        </MetricTile>
      </MetricGrid>

      <SectionPanel
        title="Adapter status"
        description="Honest reachability from existing status endpoints."
      >
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Spinner className="size-4" />
            Probing adapters…
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {probes.map((p) => (
              <div
                key={p.id}
                className="flex min-w-0 items-center justify-between gap-3 rounded-2xl border border-border bg-muted/50 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{p.label}</p>
                  <p className="mt-1 font-mono text-xs text-muted-foreground">{p.detail}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge
                    variant={p.ok ? "success" : "danger"}
                    className="rounded-full"
                  >
                    {p.ok ? "OK" : "DOWN"}
                  </Badge>
                  {p.href ? (
                    <Button asChild size="sm" variant="ghost" className="rounded-full">
                      <Link href={p.href}>Open</Link>
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionPanel>
    </OverviewTemplate>
  );
}
