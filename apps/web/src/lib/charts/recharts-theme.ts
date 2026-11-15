/**
 * One chart language for recharts across the app: recessive grid and axes,
 * brand-coloured single series, popover tooltip. All colours are CSS-variable
 * tokens so dark/light follow the theme with no per-chart code.
 */

export const CHART_SERIES = "hsl(var(--brand))";
export const CHART_INK = "hsl(var(--muted-foreground))";

export const chartGridProps = {
  stroke: "hsl(var(--border) / 0.6)",
  strokeDasharray: "2 4",
  vertical: false,
} as const;

export const chartAxisProps = {
  tick: { fill: CHART_INK, fontSize: 10, fontFamily: "var(--font-mono)" },
  axisLine: false,
  tickLine: false,
} as const;

export const chartTooltipProps = {
  cursor: { stroke: CHART_INK, strokeWidth: 1, strokeDasharray: "3 3" },
  contentStyle: {
    background: "hsl(var(--popover))",
    border: "1px solid hsl(var(--border))",
    borderRadius: 8,
    fontSize: 12,
    fontFamily: "var(--font-mono)",
    color: "hsl(var(--foreground))",
  },
  labelStyle: { color: "hsl(var(--muted-foreground))" },
  itemStyle: { color: "hsl(var(--foreground))" },
} as const;

export const chartLineProps = {
  stroke: CHART_SERIES,
  strokeWidth: 2,
  dot: false,
  activeDot: { r: 4, strokeWidth: 2, stroke: "hsl(var(--card))", fill: CHART_SERIES },
  isAnimationActive: false,
} as const;
