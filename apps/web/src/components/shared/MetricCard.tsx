import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function MetricCard({
  label,
  value,
  hint,
  tone = "default",
  className,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "profit" | "loss" | "warning";
  className?: string;
}) {
  const toneClass =
    tone === "profit"
      ? "text-[hsl(var(--profit))]"
      : tone === "loss"
        ? "text-[hsl(var(--loss))]"
        : tone === "warning"
          ? "text-[hsl(var(--warning))]"
          : "text-foreground";

  return (
    <div className={cn("cn-glow-card p-4", className)}>
      <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </p>
      <div className={cn("mt-2 font-mono text-xl tracking-tight md:text-2xl", toneClass)}>
        {value}
      </div>
      {hint ? <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
