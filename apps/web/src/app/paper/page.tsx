"use client";

import { useEffect, useState } from "react";

import { LogoLoader } from "@/components/brand/LogoLoader";
import { NumberTicker } from "@/components/magicui/number-ticker";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { localPaperFixture } from "@/lib/fixtures/agentSnapshot";
import type { PaperWorkspaceSnapshot } from "@/lib/observability/types";

export default function PaperPage() {
  const [snap, setSnap] = useState<PaperWorkspaceSnapshot | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/observability/paper", { cache: "no-store" });
        if (!res.ok) throw new Error("fail");
        const data = (await res.json()) as PaperWorkspaceSnapshot;
        if (!cancelled) setSnap(data);
      } catch {
        if (!cancelled) setSnap(localPaperFixture());
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!snap) return <LogoLoader fullScreen label="Loading paper workspace…" />;

  return (
    <div>
      <PageHeader
        title="Paper trading workspace"
        description="Virtual funds UI preview. Order submission stays disabled until a durable Python paper broker exists."
      />
      <DataModeBanner mode="demo" notes={snap.notes} />

      <div className="mb-4 grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Virtual equity</CardDescription>
            <CardTitle className="font-mono text-2xl text-primary">
              $<NumberTicker value={snap.virtual_equity} />
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Cash</CardDescription>
            <CardTitle className="font-mono text-xl">{snap.cash.toFixed(2)}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Unrealized PnL</CardDescription>
            <CardTitle className="font-mono text-xl text-[hsl(var(--profit))]">
              {snap.unrealized_pnl.toFixed(2)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Realized PnL</CardDescription>
            <CardTitle className="font-mono text-xl text-[hsl(var(--loss))]">
              {snap.realized_pnl.toFixed(2)}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Demo order entry (disabled)</CardTitle>
            <CardDescription>Preview only — never routes to Bybit</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="sym">Symbol</Label>
              <Input id="sym" defaultValue="BTCUSDT" disabled />
            </div>
            <div className="space-y-1">
              <Label htmlFor="qty">Qty</Label>
              <Input id="qty" defaultValue="0.01" disabled />
            </div>
            <Button disabled aria-disabled>
              Submit paper order (disabled)
            </Button>
            <Badge variant="warning">
              broker_implemented={String(snap.broker_implemented)}
            </Badge>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Simulated positions <Badge variant="sample">SAMPLE</Badge></CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead>Qty</TableHead>
                  <TableHead>SL</TableHead>
                  <TableHead>TP</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {snap.positions.map((p, i) => (
                  <TableRow key={i}>
                    <TableCell>{String(p.symbol)}</TableCell>
                    <TableCell>{String(p.side)}</TableCell>
                    <TableCell>{String(p.qty)}</TableCell>
                    <TableCell>{String(p.sl)}</TableCell>
                    <TableCell>{String(p.tp)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
