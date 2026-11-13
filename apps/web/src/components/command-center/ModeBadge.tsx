import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type ModeKind = "paper" | "live" | "unavailable" | "testnet" | "readonly";

const STYLES: Record<ModeKind, string> = {
  paper: "border-execution-paper/40 bg-execution-paper/10 text-foreground",
  live: "border-execution-live/40 bg-execution-live/10 text-foreground",
  unavailable: "border-destructive/40 bg-destructive/10 text-destructive",
  testnet: "border-execution-testnet/40 bg-execution-testnet/10 text-foreground",
  readonly: "border-border bg-muted text-muted-foreground",
};

const LABELS: Record<ModeKind, string> = {
  paper: "PAPER",
  live: "LIVE gated",
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
