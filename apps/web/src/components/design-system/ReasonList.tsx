import { AlertTriangle, CheckCircle2, Info, ShieldOff } from "lucide-react";

import { explainReasons, type ReasonSeverity } from "@/lib/formatting/reason-codes";
import { cn } from "@/lib/utils";

const ICON: Record<ReasonSeverity, typeof Info> = {
  ok: CheckCircle2,
  info: Info,
  warn: AlertTriangle,
  block: ShieldOff,
};

const TONE: Record<ReasonSeverity, string> = {
  ok: "text-profit",
  info: "text-muted-foreground",
  warn: "text-warning",
  block: "text-loss",
};

/**
 * Explains backend reason codes in plain language. Shows the raw code in mono
 * so operators can still grep logs.
 */
export function ReasonList({
  codes,
  compact = false,
  max,
  className,
}: {
  codes: readonly unknown[] | null | undefined;
  compact?: boolean;
  max?: number;
  className?: string;
}) {
  const items = explainReasons(codes);
  if (items.length === 0) return <p className={cn("text-xs text-muted-foreground", className)}>No reason codes.</p>;
  const shown = max ? items.slice(0, max) : items;
  return (
    <ul className={cn("space-y-1.5", className)}>
      {shown.map((item) => {
        const Icon = ICON[item.severity];
        return (
          <li key={item.code} className="flex gap-2">
            <Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", TONE[item.severity])} aria-hidden />
            <div className="min-w-0">
              <p className="text-xs font-medium text-foreground">
                {item.title}
                <span className="ml-1.5 font-mono text-[10px] font-normal text-muted-foreground">{item.code}</span>
              </p>
              {!compact && item.detail ? (
                <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{item.detail}</p>
              ) : null}
            </div>
          </li>
        );
      })}
      {max && items.length > max ? (
        <li className="text-[11px] text-muted-foreground">+{items.length - max} more</li>
      ) : null}
    </ul>
  );
}
