"use client";

import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceDescription,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from "@/components/ui/trace";

/** Subagent pattern built on Trace — a nested agent run with tools/result. */
export function Subagent({
  children,
  defaultOpen,
  open,
  onOpenChange,
  className,
}: {
  children: ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}) {
  return (
    <Trace className={className}>
      <TraceCollapsible
        defaultOpen={defaultOpen}
        open={open}
        onOpenChange={onOpenChange}
      >
        {children}
      </TraceCollapsible>
    </Trace>
  );
}

export function SubagentHeader({
  title,
  status,
  icon,
  duration,
  model,
}: {
  title: string;
  status?: "running" | "error" | "pending";
  icon?: ReactNode;
  duration?: string;
  model?: string;
}) {
  return (
    <TraceCollapsibleTrigger className="w-full max-w-full justify-between gap-2">
      <TraceLine status={status} className="min-w-0 flex-1">
        {icon ? <TraceIcon>{icon}</TraceIcon> : null}
        <TraceTitle>{title}</TraceTitle>
        {duration ? <TraceDescription>{duration}</TraceDescription> : null}
      </TraceLine>
      {model ? (
        <Badge variant="outline" className="rounded-full text-[10px]">
          {model}
        </Badge>
      ) : null}
    </TraceCollapsibleTrigger>
  );
}

export function SubagentContent({ children }: { children: ReactNode }) {
  return (
    <TraceCollapsibleContent keepMounted className="flex flex-col gap-3 text-foreground">
      {children}
    </TraceCollapsibleContent>
  );
}

export function SubagentTools({ children }: { children: ReactNode }) {
  return <Trace>{children}</Trace>;
}

export function SubagentTool({
  title,
  status,
  icon,
}: {
  title: string;
  status?: "running" | "error" | "pending";
  icon?: ReactNode;
}) {
  return (
    <TraceLine status={status}>
      {icon ? <TraceIcon>{icon}</TraceIcon> : null}
      <TraceTitle>{title}</TraceTitle>
    </TraceLine>
  );
}
