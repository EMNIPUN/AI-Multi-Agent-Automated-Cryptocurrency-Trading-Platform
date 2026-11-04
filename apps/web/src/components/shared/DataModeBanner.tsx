import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

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
    <Card className="mb-4 border-[hsl(var(--warning)/0.4)] bg-[hsl(var(--warning)/0.1)] shadow-none">
      <CardContent className="flex flex-col gap-2 p-4 sm:flex-row sm:items-start">
        <Badge variant={sample ? "sample" : "warning"}>{sample ? "SAMPLE / DEMO" : "UNAVAILABLE"}</Badge>
        <div className="text-sm text-foreground">
          <p>
            Data mode: <code className="rounded bg-muted px-1 py-0.5 text-xs">{mode}</code>.
            Not live exchange authority. Do not treat this as real-time trading activity.
          </p>
          {notes.length > 0 ? (
            <ul className="mt-1 list-disc pl-4 text-xs text-muted-foreground">
              {notes.slice(0, 3).map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
