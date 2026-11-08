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
        "overflow-hidden rounded-xl border border-white/10 bg-black/50 text-left font-mono text-white/85",
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
        "overflow-auto p-3 leading-relaxed text-white/80",
        wrap ? "whitespace-pre-wrap break-words" : "whitespace-pre",
        className,
      )}
      {...props}
    >
      {children}
    </pre>
  );
}
