import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CirclePause,
  CircleStop,
  HelpCircle,
  Hourglass,
  Radio,
  ShieldOff,
  type LucideIcon,
} from "lucide-react";

import { normalizeStatus, STATUS_LABEL, type StatusKind } from "@/lib/formatting/status";
import { cn } from "@/lib/utils";

const CONFIG: Record<StatusKind, { Icon: LucideIcon; dot: string; chip: string }> = {
  running: { Icon: Radio, dot: "bg-profit", chip: "border-profit/40 bg-profit/10 text-foreground" },
  ok: { Icon: CheckCircle2, dot: "bg-profit", chip: "border-profit/40 bg-profit/10 text-foreground" },
  idle: { Icon: CircleDashed, dot: "bg-muted-foreground", chip: "border-border bg-muted text-muted-foreground" },
  paused: { Icon: CirclePause, dot: "bg-warning", chip: "border-warning/40 bg-warning/10 text-foreground" },
  stopped: { Icon: CircleStop, dot: "bg-muted-foreground", chip: "border-border bg-muted text-muted-foreground" },
  failed: { Icon: AlertTriangle, dot: "bg-loss", chip: "border-destructive/40 bg-destructive/10 text-destructive" },
  blocked: { Icon: ShieldOff, dot: "bg-halted", chip: "border-halted/50 bg-halted/10 text-foreground" },
  unknown: { Icon: HelpCircle, dot: "bg-muted-foreground", chip: "border-border bg-muted text-muted-foreground" },
  stale: { Icon: Hourglass, dot: "bg-stale-data", chip: "border-stale-data/40 bg-stale-data/10 text-muted-foreground" },
};

export type StatusIndicatorProps = {
  /** Raw backend status (RUNNING, ERROR…) or a canonical `StatusKind`. */
  status: unknown;
  /** Override the displayed label (defaults to the canonical word). */
  label?: string;
  /** "chip" (bordered pill) or "inline" (dot + text). */
  variant?: "chip" | "inline";
  /** Pulse the dot for running states. Respects reduced motion via CSS. */
  pulse?: boolean;
  size?: "sm" | "md";
  className?: string;
  /** Extra detail after the label, e.g. "· 12s ago". */
  detail?: string;
};

/**
 * Standard status indicator. Always text + icon, never colour alone.
 * Used for workers, agents, connections, sessions and risk gates.
 */
export function StatusIndicator({
  status,
  label,
  variant = "chip",
  pulse,
  size = "sm",
  className,
  detail,
}: StatusIndicatorProps) {
  const kind = normalizeStatus(status);
  const cfg = CONFIG[kind];
  const text = label ?? STATUS_LABEL[kind];
  const Icon = cfg.Icon;
  const live = pulse && (kind === "running");

  if (variant === "inline") {
    return (
      <span className={cn("inline-flex items-center gap-1.5", size === "sm" ? "text-xs" : "text-sm", className)}>
        <span className="relative flex h-2 w-2" aria-hidden>
          {live ? <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 motion-reduce:hidden", cfg.dot)} /> : null}
          <span className={cn("relative inline-flex h-2 w-2 rounded-full", cfg.dot)} />
        </span>
        <span className="font-medium text-foreground">{text}</span>
        {detail ? <span className="text-muted-foreground">{detail}</span> : null}
        <span className="sr-only">status {STATUS_LABEL[kind]}</span>
      </span>
    );
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border font-medium",
        size === "sm" ? "px-2.5 py-0.5 text-[11px]" : "px-3 py-1 text-xs",
        cfg.chip,
        className,
      )}
      data-status={kind}
    >
      <Icon className={cn("shrink-0", size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5")} aria-hidden />
      <span>{text}</span>
      {detail ? <span className="font-normal opacity-80">{detail}</span> : null}
    </span>
  );
}

export { normalizeStatus };
