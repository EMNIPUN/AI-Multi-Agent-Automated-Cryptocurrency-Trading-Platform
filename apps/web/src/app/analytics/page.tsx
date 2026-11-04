"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { analyticsFixture } from "@/lib/fixtures/dashboard";

export default function AnalyticsPage() {
  const a = analyticsFixture;
  return (
    <div>
      <PageHeader
        title="Analytics"
        description="Equity curve, win rate, drawdown, and journal UI. SAMPLE until journals are owned."
      />
      <DataModeBanner mode="fixture" notes={[a.note]} />
      <div className="mb-4 grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Win rate</CardDescription>
            <CardTitle>{(a.winRate * 100).toFixed(1)}%</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Max drawdown</CardDescription>
            <CardTitle>{(a.maxDrawdown * 100).toFixed(1)}%</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Trades</CardDescription>
            <CardTitle>{a.trades}</CardTitle>
          </CardHeader>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Equity curve <Badge variant="sample">SAMPLE</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={a.equityCurve}>
              <CartesianGrid stroke="hsl(217 25% 20%)" strokeDasharray="3 3" />
              <XAxis dataKey="t" stroke="hsl(215 16% 65%)" fontSize={12} />
              <YAxis stroke="hsl(215 16% 65%)" fontSize={12} domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{
                  background: "hsl(222 40% 10%)",
                  border: "1px solid hsl(217 25% 22%)",
                }}
              />
              <Line
                type="monotone"
                dataKey="equity"
                stroke="hsl(160 84% 45%)"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
