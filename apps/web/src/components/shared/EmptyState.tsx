import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

import { DotPattern } from "@/components/magicui/dot-pattern";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

export function EmptyState({
  title,
  description,
  badge = "Unavailable",
  className,
  loading = false,
  icon,
  action,
}: {
  title: string;
  description: string;
  badge?: string;
  className?: string;
  loading?: boolean;
  icon?: ReactNode;
  action?: ReactNode;
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
          {loading ? (
            <Spinner className="size-4 text-muted-foreground" />
          ) : (
            (icon ?? <Inbox className="h-4 w-4 text-muted-foreground" />)
          )}
        </div>
        <Badge variant="outline" className="rounded-full">
          {loading ? (
            <span className="inline-flex items-center gap-1.5">
              <Spinner className="size-3" data-icon="inline-start" />
              Checking
            </span>
          ) : (
            badge
          )}
        </Badge>
        <h3 className="font-display text-lg">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
        {action ? <div className="mt-2">{action}</div> : null}
      </div>
    </div>
  );
}
