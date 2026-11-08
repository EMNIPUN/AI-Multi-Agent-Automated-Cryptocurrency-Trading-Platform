import { Info } from "lucide-react";

import { Badge } from "@/components/ui/badge";

export function DataModeBanner({
  mode,
  notes = [],
}: {
  mode: "fixture" | "live" | "unavailable" | "demo";
  notes?: string[];
}) {
  if (mode === "live") return null;
  const sample = mode === "fixture" || mode === "demo";
  return (
    <div className="mb-4 flex flex-col gap-2 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 sm:flex-row sm:items-start">
      <div className="flex items-center gap-2">
        <Info className="h-4 w-4 shrink-0 text-amber-400" />
        <Badge variant={sample ? "sample" : "warning"} className="rounded-full">
          {sample ? "SAMPLE / DEMO" : "UNAVAILABLE"}
        </Badge>
      </div>
      <div className="text-sm text-foreground">
        <p>
          You are viewing <span className="font-medium">{mode}</span> data — not live exchange
          authority. Safe to explore; do not treat this as real trading activity.
        </p>
        {notes.length > 0 ? (
          <ul className="mt-1.5 list-disc pl-4 text-xs text-muted-foreground">
            {notes.slice(0, 3).map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
