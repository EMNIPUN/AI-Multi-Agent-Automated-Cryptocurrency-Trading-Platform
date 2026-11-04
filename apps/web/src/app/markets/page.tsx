"use client";

import { useMemo, useState } from "react";

import { CandleChart } from "@/components/CandleChart";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { localAgentFixture } from "@/lib/fixtures/agentSnapshot";

const WATCH = [
  { symbol: "BTCUSDT", last: "—", change: "n/a" },
  { symbol: "ETHUSDT", last: "—", change: "n/a" },
  { symbol: "SOLUSDT", last: "—", change: "n/a" },
];

export default function MarketsPage() {
  const [tf, setTf] = useState("15");
  const fixture = useMemo(() => localAgentFixture(), []);

  return (
    <div>
      <PageHeader
        title="Markets"
        description="Candles and watchlist. Live ticker stats stay unavailable until a public market-data adapter is wired."
      />
      <DataModeBanner
        mode="fixture"
        notes={["Chart bars are SAMPLE fixtures", "Watchlist prices intentionally unavailable (not invented)"]}
      />
      <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              BTCUSDT <Badge variant="sample">SAMPLE CHART</Badge>
            </CardTitle>
            <Tabs value={tf} onValueChange={setTf}>
              <TabsList>
                {["1", "5", "15", "60"].map((v) => (
                  <TabsTrigger key={v} value={v}>
                    {v}m
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </CardHeader>
          <CardContent>
            <CandleChart candles={fixture.candles} markers={fixture.markers} sample />
            <p className="mt-2 text-xs text-muted-foreground">
              Selected timeframe UI: {tf}m (fixture series not re-fetched per TF yet).
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Watchlist</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {WATCH.map((w) => (
              <div
                key={w.symbol}
                className="flex items-center justify-between rounded-md border border-border/60 px-3 py-2 text-sm"
              >
                <span className="font-medium">{w.symbol}</span>
                <span className="font-mono text-muted-foreground">{w.last}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
