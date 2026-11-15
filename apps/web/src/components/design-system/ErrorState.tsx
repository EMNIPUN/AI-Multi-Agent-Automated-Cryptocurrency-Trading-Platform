import { AlertTriangle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { explainReason } from "@/lib/formatting/reason-codes";
import { formatClock, formatIso } from "@/lib/formatting/time";
import { cn } from "@/lib/utils";

export function ErrorState({
  title,
  description,
  code,
  at,
  onRetry,
  retrying,
  className,
  action,
  compact = false,
}: {
  title?: string;
  /** Human-readable explanation. Falls back to the reason-code catalog when omitted. */
  description?: string;
  /** Machine code from the API (e.g. `api_unreachable`). Shown in mono. */
  code?: string | null;
  /** When the failure happened (ms). */
  at?: number | null;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
  action?: ReactNode;
  compact?: boolean;
}) {
  const explained = code ? explainReason(code) : null;
  const heading = title ?? explained?.title ?? "Something went wrong";
  const body = description ?? explained?.detail ?? "The request did not complete.";
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-start gap-3 rounded-2xl border border-destructive/30 bg-destructive/10",
        compact ? "px-3 py-2.5" : "px-4 py-4",
        className,
      )}
    >
      <div className="flex min-w-0 items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{heading}</p>
          {body ? <p className="mt-1 text-sm text-muted-foreground">{body}</p> : null}
          {(code || at) ? (
            <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-muted-foreground">
              {code ? <span>code: {code}</span> : null}
              {at ? <span title={formatIso(at)}>at {formatClock(at)}</span> : null}
            </p>
          ) : null}
        </div>
      </div>
      {(onRetry || action) ? (
        <div className="flex flex-wrap gap-2">
          {onRetry ? (
            <Button type="button" variant="outline" size="sm" onClick={onRetry} disabled={retrying}>
              <RefreshCw className={cn("mr-1 h-3.5 w-3.5", retrying && "animate-spin")} aria-hidden />
              Retry
            </Button>
          ) : null}
          {action}
        </div>
      ) : null}
    </div>
  );
}
