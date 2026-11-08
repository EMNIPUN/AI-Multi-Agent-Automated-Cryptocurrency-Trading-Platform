"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** shadcn shimmer status text — pure CSS highlight sweep. */
export function Shimmer({
  children = "Generating response…",
  className,
  as: Comp = "p",
}: {
  children?: ReactNode;
  className?: string;
  as?: "p" | "span" | "div";
}) {
  return (
    <Comp role="status" className={cn("shimmer text-sm text-muted-foreground", className)}>
      {children}
    </Comp>
  );
}
