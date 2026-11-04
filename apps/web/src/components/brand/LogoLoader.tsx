"use client";

import { Ripple } from "@/components/magicui/ripple";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

export function LogoLoader({
  label = "Loading…",
  fullScreen = false,
  className,
}: {
  label?: string;
  fullScreen?: boolean;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={cn(
        "relative flex flex-col items-center justify-center gap-3 overflow-hidden",
        fullScreen && "min-h-[60vh] w-full",
        className,
      )}
    >
      {fullScreen ? (
        <Ripple
          mainCircleSize={80}
          mainCircleOpacity={0.22}
          numCircles={5}
          className="opacity-70"
        />
      ) : null}
      <Spinner className="relative z-[1] size-8 text-primary" />
      <p className="relative z-[1] text-sm text-muted-foreground">{label}</p>
      <span className="sr-only">{label}</span>
    </div>
  );
}
