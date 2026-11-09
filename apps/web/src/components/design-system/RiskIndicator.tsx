import { AlertTriangle, CheckCircle2, ShieldOff } from "lucide-react";

import { StatusBadge, type StatusTone } from "@/components/design-system/StatusBadge";
import { cn } from "@/lib/utils";

export function RiskIndicator({
  state,
  reason,
  className,
}: {
  state: "ok" | "blocked" | "halted" | "unknown";
  reason?: string;
  className?: string;
}) {
  const map: Record<typeof state, { tone: StatusTone; label: string; Icon: typeof CheckCircle2 }> = {
    ok: { tone: "ok", label: "Risk clear", Icon: CheckCircle2 },
    blocked: { tone: "danger", label: "Risk blocked", Icon: ShieldOff },
    halted: { tone: "halted", label: "Halted", Icon: AlertTriangle },
    unknown: { tone: "stale", label: "Risk unknown", Icon: AlertTriangle },
  };
  const cfg = map[state];
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex items-center gap-2">
        <cfg.Icon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        <StatusBadge label={cfg.label} tone={cfg.tone} />
      </div>
      {reason ? <p className="text-xs leading-relaxed text-muted-foreground">{reason}</p> : null}
    </div>
  );
}
