import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type StatusTone =
  | "neutral"
  | "ok"
  | "warn"
  | "danger"
  | "info"
  | "paper"
  | "live"
  | "halted"
  | "stale";

const TONE: Record<StatusTone, string> = {
  neutral: "border-border bg-muted text-muted-foreground",
  ok: "border-profit/40 bg-profit/10 text-foreground",
  warn: "border-warning/40 bg-warning/10 text-foreground",
  danger: "border-destructive/40 bg-destructive/10 text-destructive",
  info: "border-info/40 bg-info/10 text-foreground",
  paper: "border-paper-mode/40 bg-paper-mode/10 text-foreground",
  live: "border-live-mode/40 bg-live-mode/10 text-live-mode",
  halted: "border-halted/40 bg-halted/10 text-foreground",
  stale: "border-stale-data/40 bg-stale-data/10 text-muted-foreground",
};

export function StatusBadge({
  label,
  tone = "neutral",
  className,
}: {
  label: string;
  tone?: StatusTone;
  className?: string;
}) {
  return (
    <Badge
      variant="outline"
      className={cn("rounded-full px-2.5 py-0.5 text-[11px] font-medium", TONE[tone], className)}
    >
      {label}
    </Badge>
  );
}
