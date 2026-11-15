"use client";

import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { EquityPoint } from "@/features/dashboard/lib/equity-series";
import { formatMoney } from "@/lib/formatting/decimal";
import { formatDateTime } from "@/lib/formatting/time";

/**
 * Single-series equity curve. One hue (brand), 2px line, recessive grid,
 * crosshair tooltip. No legend: the panel title names the series.
 * Values are passed as numbers for the chart only; labels use the formatter.
 */
export function EquityCurveChart({
  points,
  currency = "USDT",
  baseline,
  height = 240,
}: {
  points: EquityPoint[];
  currency?: string;
  /** Initial balance reference line. */
  baseline?: number | null;
  height?: number;
}) {
  if (points.length === 0) return null;
  const stroke = "hsl(var(--brand))";
  const grid = "hsl(var(--border) / 0.6)";
  const ink = "hsl(var(--muted-foreground))";
  return (
    <div style={{ height }} className="w-full min-w-0" role="img" aria-label={`Realized paper equity, ${points.length} points`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.22} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={grid} strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(v: number) => new Date(v).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            tick={{ fill: ink, fontSize: 10, fontFamily: "var(--font-mono)" }}
            axisLine={false}
            tickLine={false}
            minTickGap={48}
          />
          <YAxis
            width={56}
            tickFormatter={(v: number) => formatMoney(v, 0)}
            tick={{ fill: ink, fontSize: 10, fontFamily: "var(--font-mono)" }}
            axisLine={false}
            tickLine={false}
            domain={["auto", "auto"]}
          />
          {baseline != null ? <ReferenceLine y={baseline} stroke={ink} strokeDasharray="3 3" strokeOpacity={0.6} /> : null}
          <Tooltip
            cursor={{ stroke: ink, strokeWidth: 1, strokeDasharray: "3 3" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as EquityPoint;
              return (
                <div className="rounded-lg border border-border bg-popover px-2.5 py-2 text-xs shadow-[var(--panel-shadow)]">
                  <p className="font-mono text-foreground">
                    {formatMoney(p.value)} <span className="text-muted-foreground">{currency}</span>
                  </p>
                  <p className="mt-0.5 text-muted-foreground">{formatDateTime(p.t)}</p>
                  {p.label ? <p className="text-muted-foreground">{p.label}</p> : null}
                </div>
              );
            }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={stroke}
            strokeWidth={2}
            fill="url(#equityFill)"
            dot={points.length <= 24 ? { r: 3, strokeWidth: 2, stroke: "hsl(var(--card))", fill: stroke } : false}
            activeDot={{ r: 5, strokeWidth: 2, stroke: "hsl(var(--card))", fill: stroke }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
