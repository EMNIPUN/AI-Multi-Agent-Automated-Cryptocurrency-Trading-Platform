import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function MetricTile({
  label,
  children,
  hint,
  accent,
  className,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
  accent?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("cn-metric", accent && "cn-metric-accent", className)}>
      <p className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <div className="mt-2 text-lg font-medium tracking-tight text-foreground">{children}</div>
      {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function MetricGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4", className)}>
      {children}
    </div>
  );
}
