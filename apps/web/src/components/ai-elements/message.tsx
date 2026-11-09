"use client";

import type { ComponentProps, HTMLAttributes } from "react";
import { memo } from "react";

import { cn } from "@/lib/utils";

export type MessageProps = HTMLAttributes<HTMLDivElement> & {
  from: "user" | "assistant" | "system";
};

/** AI Elements Message — role-aware chat bubble wrapper. */
export function Message({ className, from, ...props }: MessageProps) {
  return (
    <div
      className={cn(
        "group flex w-full max-w-[95%] flex-col gap-2",
        from === "user" ? "is-user ml-auto justify-end" : "is-assistant",
        className,
      )}
      data-role={from}
      {...props}
    />
  );
}

export type MessageContentProps = HTMLAttributes<HTMLDivElement>;

export function MessageContent({ className, children, ...props }: MessageContentProps) {
  return (
    <div
      className={cn(
        "flex w-fit min-w-0 max-w-full flex-col gap-2 overflow-hidden text-sm",
        "group-[.is-user]:ml-auto group-[.is-user]:rounded-2xl group-[.is-user]:bg-primary group-[.is-user]:px-4 group-[.is-user]:py-3 group-[.is-user]:text-primary-foreground",
        "group-[.is-assistant]:rounded-2xl group-[.is-assistant]:border group-[.is-assistant]:border-border group-[.is-assistant]:bg-card group-[.is-assistant]:px-4 group-[.is-assistant]:py-3 group-[.is-assistant]:text-foreground",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export type MessageResponseProps = ComponentProps<"div"> & {
  isAnimating?: boolean;
};

/** Lightweight text response (no Streamdown dependency). */
export const MessageResponse = memo(function MessageResponse({
  className,
  children,
  isAnimating,
  ...props
}: MessageResponseProps) {
  return (
    <div
      className={cn(
        "size-full whitespace-pre-wrap leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
        isAnimating && "opacity-90",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
});
