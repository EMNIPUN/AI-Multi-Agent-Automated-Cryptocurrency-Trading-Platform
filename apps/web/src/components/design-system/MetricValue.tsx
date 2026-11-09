import { cn } from "@/lib/utils";

export function MetricValue({
  value,
  suffix,
  tone = "default",
  className,
}: {
  value: React.ReactNode;
  suffix?: string;
  tone?: "default" | "profit" | "loss" | "muted";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "font-mono tabular-nums tracking-tight",
        tone === "profit" && "text-profit",
        tone === "loss" && "text-loss",
        tone === "muted" && "text-muted-foreground",
        tone === "default" && "text-foreground",
        className,
      )}
    >
      {value}
      {suffix ? <span className="ml-1 text-xs text-muted-foreground">{suffix}</span> : null}
    </span>
  );
}
