"use client";

import type { ReactNode } from "react";

import {
  Trace,
  TraceCollapsible,
  TraceCollapsibleContent,
  TraceCollapsibleTrigger,
  TraceIcon,
  TraceLine,
  TraceTitle,
} from "@/components/ui/trace";

/** Task pattern built on Trace — collapsible work with nested steps. */
export function Task({
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

export function TaskTrigger({
  title,
  status,
  icon,
}: {
  title: string;
  status?: "running" | "error" | "pending";
  icon?: ReactNode;
}) {
  return (
    <TraceCollapsibleTrigger>
      <TraceLine status={status}>
        {icon ? <TraceIcon>{icon}</TraceIcon> : null}
        <TraceTitle>{title}</TraceTitle>
      </TraceLine>
    </TraceCollapsibleTrigger>
  );
}

export function TaskContent({ children }: { children: ReactNode }) {
  return (
    <TraceCollapsibleContent keepMounted>
      <Trace>{children}</Trace>
    </TraceCollapsibleContent>
  );
}

export function TaskItem({
  title,
  status,
  icon,
  onClick,
}: {
  title: string;
  status?: "running" | "error" | "pending";
  icon?: ReactNode;
  onClick?: () => void;
}) {
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className="text-left">
        <TraceLine status={status}>
          {icon ? <TraceIcon>{icon}</TraceIcon> : null}
          <TraceTitle>{title}</TraceTitle>
        </TraceLine>
      </button>
    );
  }

  return (
    <TraceLine status={status}>
      {icon ? <TraceIcon>{icon}</TraceIcon> : null}
      <TraceTitle>{title}</TraceTitle>
    </TraceLine>
  );
}
