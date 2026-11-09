import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type ModeKind = "paper" | "live" | "unavailable" | "testnet" | "readonly";

const STYLES: Record<ModeKind, string> = {
  paper: "border-brand/40 bg-brand/10 text-foreground",
  live: "border-rose-400/50 bg-rose-400/15 text-destructive",
  unavailable: "border-rose-400/30 bg-rose-400/10 text-rose-600 dark:text-destructive",
  testnet: "border-brand/40 bg-brand/10 text-foreground",
  readonly: "border-brand/35 bg-brand/10 text-foreground",
};

const LABELS: Record<ModeKind, string> = {
  paper: "PAPER",
  live: "LIVE",
  unavailable: "Unavailable",
  testnet: "Testnet",
  readonly: "Read-only",
};

export function ModeBadge({
  mode,
  label,
  className,
}: {
  mode: ModeKind;
  label?: string;
  className?: string;
}) {
  return (
    <Badge variant="outline" className={cn("rounded-full", STYLES[mode], className)}>
      {label ?? LABELS[mode]}
    </Badge>
  );
}
