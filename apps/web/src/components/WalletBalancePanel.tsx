"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Wallet } from "lucide-react";

import { LogoLoader } from "@/components/brand/LogoLoader";
import { NumberTicker } from "@/components/magicui/number-ticker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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

export function WalletBalancePanel() {
  const [status, setStatus] = useState<Status>("loading");
  const [wallet, setWallet] = useState<ExchangeWalletSnapshot | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setStatus("loading");
    setError("");
    try {
      const res = await fetch("/api/exchange/wallet", { cache: "no-store" });
      const body = await res.json();
      if (res.status === 403) {
        setStatus("disabled");
        setError(String(body.detail || "exchange_wallet_reads_disabled"));
        return;
      }
      if (!res.ok) {
        setStatus("error");
        setError(String(body.detail || `http_${res.status}`));
        return;
      }
      setWallet(body as ExchangeWalletSnapshot);
      setStatus("ready");
    } catch {
      setStatus("error");
      setError("api_unreachable");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Wallet className="h-4 w-4 text-primary" />
            Bybit UNIFIED wallet
          </CardTitle>
          <CardDescription>
            Server-side read-only adapter · API keys never enter the browser bundle
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => void load()}>
          <RefreshCw className="mr-1 h-3.5 w-3.5" />
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
        {status === "loading" ? (
          <LogoLoader label="Fetching Bybit wallet…" className="py-6" />
        ) : null}

        {status === "disabled" ? (
          <Badge variant="warning">Wallet reads disabled ({error})</Badge>
        ) : null}

        {status === "error" ? (
          <div className="space-y-2">
            <Badge variant="danger">Unavailable: {error}</Badge>
            <p className="text-xs text-muted-foreground">
              Start FastAPI on 127.0.0.1:8000. Showing no invented balances.
            </p>
          </div>
        ) : null}

        {status === "ready" && wallet ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{wallet.env_label}</Badge>
              {wallet.is_mainnet ? <Badge variant="danger">MAINNET</Badge> : null}
              <Badge variant="secondary">{wallet.account_type}</Badge>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <div className="text-xs text-muted-foreground">Total equity</div>
                <div className="font-mono text-2xl text-primary">
                  <NumberTicker value={Number(wallet.total_equity || 0)} />
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Wallet balance</div>
                <div className="font-mono text-lg">{wallet.total_wallet_balance ?? "—"}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Perp uPnL</div>
                <div className="font-mono text-lg">{wallet.total_perp_upl ?? "—"}</div>
              </div>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Coin</TableHead>
                  <TableHead>Wallet</TableHead>
                  <TableHead>Available</TableHead>
                  <TableHead>Equity</TableHead>
                  <TableHead>uPnL</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {wallet.coins.map((c) => (
                  <TableRow key={c.coin}>
                    <TableCell>{c.coin}</TableCell>
                    <TableCell>{c.wallet_balance}</TableCell>
                    <TableCell>{c.available}</TableCell>
                    <TableCell>{c.equity}</TableCell>
                    <TableCell>{c.unrealised_pnl}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="text-[11px] text-muted-foreground">
              Fetched {new Date(wallet.fetched_at).toISOString()} · ownership of exchange
              account not multi-tenant yet — treat as operator-local read.
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
