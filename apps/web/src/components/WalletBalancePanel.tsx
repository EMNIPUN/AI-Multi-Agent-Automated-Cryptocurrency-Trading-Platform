"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { RefreshCw, Wallet } from "lucide-react";

import { BorderBeam } from "@/components/magicui/border-beam";
import { NumberTicker } from "@/components/magicui/number-ticker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

export interface WalletCoin {
  coin: string;
  wallet_balance: string;
  equity: string;
  available: string;
  unrealised_pnl: string;
}

export interface ExchangeWalletSnapshot {
  schema_version: string;
  source: string;
  account_type: string;
  env_label: string;
  is_mainnet: boolean;
  fetched_at: string;
  total_equity: string | null;
  total_wallet_balance: string | null;
  total_available_balance: string | null;
  total_perp_upl: string | null;
  coins: WalletCoin[];
  notes: string[];
}

type Status = "loading" | "ready" | "error" | "disabled";
type CoinFilter = "all" | "majors" | "pnl" | "dust";

const MAJORS = new Set(["BTC", "ETH", "USDT", "USDC", "SOL"]);

function friendlyWalletError(error: string) {
  switch (error) {
    case "authentication_required":
      return "Wallet reading needs a local setup step. Check Settings → Exchanges.";
    case "ownership_schema_required":
      return "Wallet ownership checks are still gated. Try again after setup.";
    case "exchange_binding_missing":
      return "No exchange account is linked yet. Connect one in Settings → Exchanges.";
    case "exchange_binding_inactive":
      return "Your exchange link is inactive. Reconnect it in Settings.";
    case "exchange_wallet_reads_disabled":
      return "Wallet reads are turned off on the server.";
    case "credential_material_unavailable":
    case "credential_ref_unknown":
      return "Exchange credentials aren’t available on the server.";
    case "bybit_credentials_missing":
      return "Bybit API keys are missing on the server.";
    case "api_unreachable":
      return "Can’t reach the API right now. Start FastAPI and refresh.";
    default:
      return error;
  }
}

function asNumber(value: string | null | undefined) {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function formatQty(value: string | null | undefined) {
  const n = asNumber(value);
  if (n == null) return "—";
  if (Math.abs(n) > 0 && Math.abs(n) < 0.0001) return n.toExponential(2);
  return n.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

function pnlTone(value: string | null | undefined) {
  const n = asNumber(value);
  if (n == null) return "text-muted-foreground";
  if (n > 0) return "text-emerald-400";
  if (n < 0) return "text-rose-400";
  return "text-muted-foreground";
}

function coinShare(coin: WalletCoin, totalEquity: number | null) {
  if (!totalEquity || totalEquity <= 0) return null;
  return ((asNumber(coin.equity) ?? 0) / totalEquity) * 100;
}

function WalletSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading wallet">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-2xl border border-border bg-muted/40 p-4">
            <Skeleton className="h-3 w-20 rounded-full" />
            <Skeleton className="mt-3 h-8 w-28 rounded-md" />
          </div>
        ))}
      </div>
      <Skeleton className="h-48 w-full rounded-2xl" />
    </div>
  );
}

function FilterChip({
  active,
  children,
  onClick,
  count,
}: {
  active?: boolean;
  children: ReactNode;
  onClick: () => void;
  count?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
        active
          ? "bg-primary text-primary-foreground"
          : "bg-muted/40 text-foreground hover:bg-muted/40 hover:text-foreground",
      )}
    >
      {children}
      {typeof count === "number" ? (
        <span className={cn("ml-1.5 tabular-nums", active ? "text-black/60" : "text-foreground")}>
          {count}
        </span>
      ) : null}
    </button>
  );
}

/**
 * Personal-use wallet panel: omit Authorization so FastAPI uses operator-local
 * loopback (server BYBIT_* keys). A user JWT would force gated owner-bound reads.
 */
export function WalletBalancePanel({ compact = false }: { compact?: boolean }) {
  const [status, setStatus] = useState<Status>("loading");
  const [wallet, setWallet] = useState<ExchangeWalletSnapshot | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [selectedCoin, setSelectedCoin] = useState<string | null>(null);
  const [view, setView] = useState<"overview" | "holdings">("overview");
  const [filter, setFilter] = useState<CoinFilter>("all");

  const load = useCallback(async (soft = false) => {
    if (soft) setRefreshing(true);
    else setStatus("loading");
    setError("");
    try {
      const res = await fetch("/api/exchange/wallet", {
        cache: "no-store",
      });
      const body = await res.json();
      if (res.status === 401 || res.status === 403) {
        setStatus("disabled");
        setError(String(body.detail || body.message || "exchange_wallet_reads_disabled"));
        setWallet(null);
        return;
      }
      if (!res.ok) {
        setStatus("error");
        setError(String(body.detail || `http_${res.status}`));
        return;
      }
      const snap = body as ExchangeWalletSnapshot;
      setWallet(snap);
      setSelectedCoin((prev) => prev ?? snap.coins[0]?.coin ?? null);
      setStatus("ready");
    } catch {
      setStatus("error");
      setError("api_unreachable");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const totalEquity = asNumber(wallet?.total_equity);

  const coins = useMemo(() => {
    if (!wallet) return [];
    return [...wallet.coins].sort(
      (a, b) => (asNumber(b.equity) ?? 0) - (asNumber(a.equity) ?? 0),
    );
  }, [wallet]);

  const filterCounts = useMemo(() => {
    const majors = coins.filter((c) => MAJORS.has(c.coin.toUpperCase())).length;
    const pnl = coins.filter((c) => (asNumber(c.unrealised_pnl) ?? 0) !== 0).length;
    const dust = coins.filter((c) => {
      const share = coinShare(c, totalEquity);
      return share != null && share > 0 && share < 1;
    }).length;
    return { all: coins.length, majors, pnl, dust };
  }, [coins, totalEquity]);

  const filteredCoins = useMemo(() => {
    return coins.filter((c) => {
      if (filter === "majors") return MAJORS.has(c.coin.toUpperCase());
      if (filter === "pnl") return (asNumber(c.unrealised_pnl) ?? 0) !== 0;
      if (filter === "dust") {
        const share = coinShare(c, totalEquity);
        return share != null && share > 0 && share < 1;
      }
      return true;
    });
  }, [coins, filter, totalEquity]);

  const selected =
    filteredCoins.find((c) => c.coin === selectedCoin) ??
    coins.find((c) => c.coin === selectedCoin) ??
    filteredCoins[0] ??
    null;

  const selectedShare = selected ? coinShare(selected, totalEquity) : null;

  const topHoldings = coins.slice(0, 5);
  const metrics: Array<{
    label: string;
    value: string | null | undefined;
    emphasize?: boolean;
    pnl?: boolean;
  }> = [
    { label: "Total equity", value: wallet?.total_equity, emphasize: true },
    { label: "Wallet balance", value: wallet?.total_wallet_balance },
    { label: "Available", value: wallet?.total_available_balance },
    { label: "Open P&L", value: wallet?.total_perp_upl, pnl: true },
  ];

  useEffect(() => {
    if (!selectedCoin) return;
    if (filteredCoins.some((c) => c.coin === selectedCoin)) return;
    setSelectedCoin(filteredCoins[0]?.coin ?? null);
  }, [filteredCoins, selectedCoin]);

  return (
    <section
      className={cn(
        "relative overflow-hidden rounded-3xl border border-border/70 bg-card/60 p-5 md:p-6",
        compact && "p-5",
      )}
    >
      <BorderBeam size={190} duration={13} colorFrom="#F7A600" colorTo="#FFCE6E" />
      <div className="relative z-10 flex flex-row items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-display text-xl tracking-tight">
            <Wallet className="h-4 w-4 text-foreground" />
            Exchange wallet
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Read-only Bybit UNIFIED balance · keys stay on the server
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="rounded-full"
          onClick={() => void load(true)}
          disabled={refreshing || status === "loading"}
        >
          {refreshing ? <Spinner className="mr-1" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
          Refresh
        </Button>
      </div>

      <div className="relative z-10 mt-5">
        {status === "loading" ? <WalletSkeleton /> : null}

        {status === "disabled" || status === "error" ? (
          <div className="rounded-2xl border border-border/60 bg-background/40 px-4 py-5">
            <Badge variant={status === "disabled" ? "warning" : "danger"} className="rounded-full">
              {status === "disabled" ? "Not connected" : "Unavailable"}
            </Badge>
            <p className="mt-3 text-sm text-muted-foreground">{friendlyWalletError(error)}</p>
          </div>
        ) : null}

        {status === "ready" && wallet ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="rounded-full">
                {wallet.is_mainnet ? "Live network" : "Test network"}
              </Badge>
              <Badge variant="secondary" className="rounded-full">
                {wallet.env_label}
              </Badge>
              <Badge variant="outline" className="rounded-full">
                {wallet.account_type}
              </Badge>
              <Badge variant="secondary" className="rounded-full">
                {wallet.source}
              </Badge>
              <Badge variant="outline" className="rounded-full">
                Read only
              </Badge>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {metrics.map((m) => (
                <div
                  key={m.label}
                  className={cn(
                    "rounded-2xl border p-4",
                    m.emphasize
                      ? "border-border bg-muted/40"
                      : "border-border/60 bg-background/40",
                  )}
                >
                  <p className="text-xs text-muted-foreground">{m.label}</p>
                  <p
                    className={cn(
                      "mt-1 font-mono",
                      m.emphasize ? "text-2xl text-foreground" : "text-lg",
                      m.pnl ? pnlTone(m.value) : undefined,
                    )}
                  >
                    {m.emphasize && asNumber(m.value) != null ? (
                      <NumberTicker value={asNumber(m.value)!} decimalPlaces={2} />
                    ) : (
                      formatQty(m.value)
                    )}
                  </p>
                </div>
              ))}
            </div>

            {compact ? (
              <ScrollArea className="max-h-64 rounded-2xl border border-border/60">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Coin</TableHead>
                      <TableHead>Equity</TableHead>
                      <TableHead>Share</TableHead>
                      <TableHead>Open P&L</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {coins.slice(0, 5).map((c) => {
                      const share = coinShare(c, totalEquity);
                      return (
                        <TableRow key={c.coin}>
                          <TableCell className="font-medium">{c.coin}</TableCell>
                          <TableCell className="font-mono">{formatQty(c.equity)}</TableCell>
                          <TableCell className="font-mono text-muted-foreground">
                            {share == null ? "—" : `${share.toFixed(1)}%`}
                          </TableCell>
                          <TableCell className={cn("font-mono", pnlTone(c.unrealised_pnl))}>
                            {formatQty(c.unrealised_pnl)}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </ScrollArea>
            ) : (
              <Tabs
                value={view}
                onValueChange={(value) => setView(value as "overview" | "holdings")}
              >
                <TabsList className="w-auto" aria-label="Portfolio views">
                  <TabsTrigger value="overview">Overview</TabsTrigger>
                  <TabsTrigger value="holdings">Holdings</TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="mt-4 space-y-4">
                  <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
                    <div className="rounded-2xl border border-border bg-muted/50 p-4">
                      <div className="mb-3 flex items-center justify-between gap-2">
                        <div>
                          <p className="text-sm font-medium text-foreground">Top holdings</p>
                          <p className="text-xs text-muted-foreground">
                            Largest equity share from Bybit snapshot
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="rounded-full"
                          onClick={() => setView("holdings")}
                        >
                          View all
                        </Button>
                      </div>
                      <ScrollArea className="h-56">
                        <div className="space-y-2 pr-3">
                          {topHoldings.map((c) => {
                            const share = coinShare(c, totalEquity) ?? 0;
                            return (
                              <button
                                key={c.coin}
                                type="button"
                                onClick={() => {
                                  setSelectedCoin(c.coin);
                                  setView("holdings");
                                }}
                                className="w-full rounded-xl border border-border bg-muted/40 px-3 py-2.5 text-left transition-colors hover:bg-muted/40"
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <span className="font-medium text-foreground">{c.coin}</span>
                                  <span className="font-mono text-xs text-foreground">
                                    {share.toFixed(1)}%
                                  </span>
                                </div>
                                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted/40">
                                  <div
                                    className="h-full rounded-full bg-amber-400/80"
                                    style={{ width: `${Math.min(100, share)}%` }}
                                  />
                                </div>
                                <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
                                  <span className="font-mono">{formatQty(c.equity)}</span>
                                  <span className={cn("font-mono", pnlTone(c.unrealised_pnl))}>
                                    P&L {formatQty(c.unrealised_pnl)}
                                  </span>
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      </ScrollArea>
                    </div>

                    <div className="rounded-2xl border border-border bg-muted/50 p-4">
                      <p className="text-sm font-medium text-foreground">Snapshot</p>
                      <p className="text-xs text-muted-foreground">Account facts from the API</p>
                      <Separator className="my-3 bg-muted/40" />
                      <ScrollArea className="h-56">
                        <dl className="space-y-2 pr-3 text-sm">
                          {[
                            ["Coins", String(coins.length)],
                            ["Majors", String(filterCounts.majors)],
                            ["With open P&L", String(filterCounts.pnl)],
                            ["Dust (<1%)", String(filterCounts.dust)],
                            ["Account", wallet.account_type],
                            ["Environment", wallet.env_label],
                            ["Network", wallet.is_mainnet ? "Mainnet" : "Testnet"],
                            ["Source", wallet.source],
                            ["Schema", wallet.schema_version],
                            ["Fetched", new Date(wallet.fetched_at).toLocaleString()],
                          ].map(([label, value]) => (
                            <div
                              key={label}
                              className="flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/40 px-3 py-2"
                            >
                              <dt className="text-muted-foreground">{label}</dt>
                              <dd className="font-mono text-foreground">{value}</dd>
                            </div>
                          ))}
                        </dl>
                      </ScrollArea>
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="holdings" className="mt-4 space-y-3">
                  <div className="flex flex-wrap items-center gap-1.5 rounded-full border border-border bg-muted/70 p-1.5">
                    <FilterChip
                      active={filter === "all"}
                      count={filterCounts.all}
                      onClick={() => setFilter("all")}
                    >
                      All
                    </FilterChip>
                    <FilterChip
                      active={filter === "majors"}
                      count={filterCounts.majors}
                      onClick={() => setFilter("majors")}
                    >
                      Majors
                    </FilterChip>
                    <FilterChip
                      active={filter === "pnl"}
                      count={filterCounts.pnl}
                      onClick={() => setFilter("pnl")}
                    >
                      With P&L
                    </FilterChip>
                    <FilterChip
                      active={filter === "dust"}
                      count={filterCounts.dust}
                      onClick={() => setFilter("dust")}
                    >
                      Dust
                    </FilterChip>
                  </div>

                  <div className="h-[28rem] overflow-hidden rounded-2xl border border-border bg-muted/50">
                    <ResizablePanelGroup direction="horizontal" className="h-full">
                      <ResizablePanel defaultSize={62} minSize={40}>
                        <div className="flex h-full flex-col">
                          <div className="flex items-center justify-between gap-2 px-4 py-3">
                            <div>
                              <p className="text-sm font-medium text-foreground">Holdings</p>
                              <p className="text-xs text-muted-foreground">
                                Showing {filteredCoins.length} of {coins.length}
                              </p>
                            </div>
                          </div>
                          <Separator className="bg-muted/40" />
                          <ScrollArea className="min-h-0 flex-1">
                            {filteredCoins.length === 0 ? (
                              <p className="px-4 py-10 text-center text-sm text-muted-foreground">
                                No coins match this filter.
                              </p>
                            ) : (
                              <Table>
                                <TableHeader>
                                  <TableRow>
                                    <TableHead>Coin</TableHead>
                                    <TableHead>Wallet</TableHead>
                                    <TableHead>Available</TableHead>
                                    <TableHead>Equity</TableHead>
                                    <TableHead>Share</TableHead>
                                    <TableHead>Open P&L</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {filteredCoins.map((c) => {
                                    const share = coinShare(c, totalEquity);
                                    const active = selected?.coin === c.coin;
                                    return (
                                      <TableRow
                                        key={c.coin}
                                        className={cn("cursor-pointer", active && "bg-muted/40")}
                                        onClick={() => setSelectedCoin(c.coin)}
                                        data-state={active ? "selected" : undefined}
                                      >
                                        <TableCell className="font-medium">{c.coin}</TableCell>
                                        <TableCell className="font-mono">
                                          {formatQty(c.wallet_balance)}
                                        </TableCell>
                                        <TableCell className="font-mono">
                                          {formatQty(c.available)}
                                        </TableCell>
                                        <TableCell className="font-mono">
                                          {formatQty(c.equity)}
                                        </TableCell>
                                        <TableCell className="font-mono text-muted-foreground">
                                          {share == null ? "—" : `${share.toFixed(1)}%`}
                                        </TableCell>
                                        <TableCell
                                          className={cn("font-mono", pnlTone(c.unrealised_pnl))}
                                        >
                                          {formatQty(c.unrealised_pnl)}
                                        </TableCell>
                                      </TableRow>
                                    );
                                  })}
                                </TableBody>
                              </Table>
                            )}
                          </ScrollArea>
                        </div>
                      </ResizablePanel>
                      <ResizableHandle withHandle />
                      <ResizablePanel defaultSize={38} minSize={26}>
                        <div className="flex h-full flex-col p-4">
                          <p className="text-sm font-medium text-foreground">Coin detail</p>
                          <p className="text-xs text-muted-foreground">
                            Select a row to inspect Bybit balances
                          </p>
                          <Separator className="my-3 bg-muted/40" />
                          <ScrollArea className="min-h-0 flex-1">
                            {selected ? (
                              <div className="space-y-3 pr-3">
                                <div className="flex items-center justify-between gap-2">
                                  <h3 className="text-2xl font-medium tracking-tight text-foreground">
                                    {selected.coin}
                                  </h3>
                                  <Badge variant="outline" className="rounded-full">
                                    {selectedShare == null
                                      ? "—"
                                      : `${selectedShare.toFixed(2)}%`}
                                  </Badge>
                                </div>
                                <div className="h-2 overflow-hidden rounded-full bg-muted/40">
                                  <div
                                    className="h-full rounded-full bg-amber-400/80"
                                    style={{
                                      width: `${Math.min(100, Math.max(0, selectedShare ?? 0))}%`,
                                    }}
                                  />
                                </div>
                                <dl className="space-y-2 text-sm">
                                  {[
                                    ["Wallet balance", selected.wallet_balance],
                                    ["Available to withdraw", selected.available],
                                    ["Equity", selected.equity],
                                    ["Unrealised P&L", selected.unrealised_pnl],
                                  ].map(([label, value]) => (
                                    <div
                                      key={label}
                                      className="flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/40 px-3 py-2"
                                    >
                                      <dt className="text-muted-foreground">{label}</dt>
                                      <dd
                                        className={cn(
                                          "font-mono text-foreground",
                                          label.includes("P&L") ? pnlTone(value) : undefined,
                                        )}
                                      >
                                        {formatQty(value)}
                                      </dd>
                                    </div>
                                  ))}
                                </dl>
                              </div>
                            ) : (
                              <p className="text-sm text-muted-foreground">No coin selected.</p>
                            )}
                          </ScrollArea>
                        </div>
                      </ResizablePanel>
                    </ResizablePanelGroup>
                  </div>
                </TabsContent>
              </Tabs>
            )}

            {wallet.notes.length > 0 ? (
              <ul className="list-disc space-y-1 pl-4 text-[11px] text-muted-foreground">
                {wallet.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            ) : null}

            <p className="text-[11px] text-muted-foreground">
              Updated {new Date(wallet.fetched_at).toLocaleString()} · schema{" "}
              {wallet.schema_version} · never shown as zero when the API fails
            </p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
