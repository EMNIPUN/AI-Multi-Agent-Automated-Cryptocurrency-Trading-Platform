import { Inbox } from "lucide-react";

import { DotPattern } from "@/components/magicui/dot-pattern";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function EmptyState({
  title,
  description,
  badge = "Unavailable",
  className,
}: {
  title: string;
  description: string;
  badge?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border border-dashed border-border bg-card/40 p-8 text-center",
        className,
      )}
    >
      <DotPattern className="opacity-40" />
      <div className="relative mx-auto flex max-w-md flex-col items-center gap-2">
        <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-background/70">
          <Inbox className="h-4 w-4 text-muted-foreground" />
        </div>
        <Badge variant="outline">{badge}</Badge>
        <h3 className="font-display text-lg">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}
