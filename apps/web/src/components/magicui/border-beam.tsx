"use client";

import { useReducedMotion } from "motion/react";

import { cn } from "@/lib/utils";

/** Magic UI–style Border Beam for active/important cards. */
export function BorderBeam({
  className,
  size = 180,
  duration = 8,
  colorFrom = "hsl(160 84% 45%)",
  colorTo = "hsl(217 91% 60%)",
}: {
  className?: string;
  size?: number;
  duration?: number;
  colorFrom?: string;
  colorTo?: string;
}) {
  const reduce = useReducedMotion();
  if (reduce) return null;

  return (
    <div
      style={
        {
          "--size": size,
          "--duration": duration,
          "--color-from": colorFrom,
          "--color-to": colorTo,
        } as React.CSSProperties
      }
      className={cn(
        "pointer-events-none absolute inset-0 rounded-[inherit] [mask-clip:padding-box,border-box] [mask-composite:intersect] [mask-image:linear-gradient(transparent,transparent),linear-gradient(#000,#000)]",
        className,
      )}
    >
      <div
        className="absolute aspect-square w-[calc(var(--size)*1px)] animate-border-beam [background:linear-gradient(to_left,var(--color-from),var(--color-to),transparent)] [offset-anchor:100%_50%] [offset-path:rect(0_auto_auto_0_round_calc(var(--size)*1px))]"
      />
    </div>
  );
}
