"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

export function CodeBlock({
  className,
  size = "md",
  children,
  ...props
}: React.ComponentProps<"div"> & { size?: "sm" | "md" }) {
  return (
    <div
      data-slot="code-block"
      className={cn(
        "overflow-hidden rounded-xl border border-border bg-muted/80 text-left font-mono text-foreground",
        size === "sm" ? "text-[11px]" : "text-xs",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CodeBlockContent({
  className,
  wrap = false,
  children,
  ...props
}: React.ComponentProps<"pre"> & { wrap?: boolean }) {
  return (
    <pre
      data-slot="code-block-content"
      className={cn(
        "overflow-auto p-3 leading-relaxed text-foreground",
        wrap ? "whitespace-pre-wrap break-words" : "whitespace-pre",
        className,
      )}
      {...props}
    >
      {children}
    </pre>
  );
}
