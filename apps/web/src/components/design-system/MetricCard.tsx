import type { ElementType, ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export type MetricCardProps = {
  label: string;
  /** Main value. Pass a `FinancialValue` for money, or any node. */
  value: ReactNode;
  /** Secondary line under the value. */
  hint?: ReactNode;
  /** Small delta / status chip rendered next to the label. */
  badge?: ReactNode;
  icon?: ElementType;
  /** Amber accent border for the primary metric. */
  accent?: boolean;
  /** Render a skeleton instead of the value. */
  loading?: boolean;
  /** Visually de-emphasise when the source is unavailable. */
  muted?: boolean;
  className?: string;
};

/**
 * KPI tile. One per metric; label small-caps, value large mono. Loading and
 * unavailable states are explicit so the grid never shows fake numbers.
 */
export function MetricCard({ label, value, hint, badge, icon: Icon, accent, loading, muted, className }: MetricCardProps) {
  return (
    <div
      className={cn(
        "cn-metric flex min-w-0 flex-col justify-between gap-2",
        accent && "cn-metric-accent",
        muted && "opacity-75",
        className,
      )}
      aria-busy={loading || undefined}
    >
      <div className="flex min-w-0 items-start justify-between gap-2">
        <p className="flex min-w-0 items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
          {Icon ? <Icon className="h-3.5 w-3.5 shrink-0 opacity-80" aria-hidden /> : null}
          <span className="truncate">{label}</span>
        </p>
        {badge ? <div className="shrink-0">{badge}</div> : null}
      </div>
      <div className="min-w-0 text-xl font-medium leading-tight tracking-tight text-foreground md:text-2xl">
        {loading ? <Skeleton className="h-7 w-28 rounded-md" /> : value}
      </div>
      {hint ? <div className="min-w-0 truncate text-xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

export function MetricCardGrid({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4", className)}>{children}</div>;
}
