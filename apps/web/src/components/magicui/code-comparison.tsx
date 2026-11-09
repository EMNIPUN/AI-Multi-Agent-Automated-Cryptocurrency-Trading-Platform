"use client";

import { FileIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type CodeComparisonProps = {
  beforeCode: string;
  afterCode: string;
  language?: string;
  filename: string;
  beforeLabel?: string;
  afterLabel?: string;
  className?: string;
};

/**
 * Side-by-side comparison panel (Magic UI–style).
 * Plain monospace rendering — no Shiki dependency for local dashboard use.
 */
export function CodeComparison({
  beforeCode,
  afterCode,
  filename,
  beforeLabel = "before",
  afterLabel = "after",
  className,
}: CodeComparisonProps) {
  return (
    <div className={cn("mx-auto w-full", className)}>
      <div className="group relative w-full overflow-hidden rounded-xl border border-border bg-muted/70">
        <div className="relative grid md:grid-cols-2">
          <div className="border-border md:border-r">
            <div className="flex items-center border-b border-border bg-muted/40 px-3 py-2 text-sm text-foreground">
              <FileIcon className="mr-2 h-4 w-4 text-amber-200/70" />
              {filename}
              <span className="ml-auto hidden text-xs text-muted-foreground md:block">
                {beforeLabel}
              </span>
            </div>
            <pre className="max-h-[28rem] overflow-auto p-4 font-mono text-[11px] leading-relaxed text-foreground whitespace-pre-wrap break-all">
              {beforeCode}
            </pre>
          </div>
          <div className="border-t border-border md:border-t-0">
            <div className="flex items-center border-b border-border bg-muted/40 px-3 py-2 text-sm text-foreground">
              <FileIcon className="mr-2 h-4 w-4 text-amber-200/70" />
              {filename}
              <span className="ml-auto hidden text-xs text-muted-foreground md:block">
                {afterLabel}
              </span>
            </div>
            <pre className="max-h-[28rem] overflow-auto p-4 font-mono text-[11px] leading-relaxed text-foreground whitespace-pre-wrap break-all">
              {afterCode}
            </pre>
          </div>
        </div>
        <div className="absolute left-1/2 top-1/2 hidden h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-md border border-border bg-zinc-950 text-xs text-foreground md:flex">
          VS
        </div>
      </div>
    </div>
  );
}
