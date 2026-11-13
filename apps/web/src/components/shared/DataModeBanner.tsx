import { Info } from "lucide-react";

import { Badge } from "@/components/ui/badge";

export function DataModeBanner({
  mode,
  notes = [],
}: {
  mode: "fixture" | "live" | "unavailable" | "demo" | "paper";
  notes?: string[];
}) {
  if (mode === "live") return null;
  const sample = mode === "fixture" || mode === "demo";
  const paper = mode === "paper";
  return (
    <div className="mb-4 flex flex-col gap-2 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 sm:flex-row sm:items-start">
      <div className="flex items-center gap-2">
        <Info className="h-4 w-4 shrink-0 text-warning" />
        <Badge variant={sample || paper ? "sample" : "warning"} className="rounded-full">
          {sample ? "SAMPLE / DEMO" : paper ? "PAPER" : "UNAVAILABLE"}
        </Badge>
      </div>
      <div className="text-sm text-foreground">
        <p>
          {paper
            ? "Paper supervision data. This is not exchange execution authority."
            : sample
              ? "Sample data only. This is not live exchange authority."
              : "This feed is unavailable. Nothing here is live exchange authority."}
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
