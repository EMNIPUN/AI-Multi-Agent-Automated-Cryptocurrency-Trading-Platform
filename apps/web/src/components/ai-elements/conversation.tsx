"use client";

import type { ComponentProps, ReactNode } from "react";

import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import { cn } from "@/lib/utils";

/**
 * AI Elements Conversation — now backed by shadcn Message Scroller (Chat pattern).
 * Keep export names stable for existing call sites.
 */
export type ConversationProps = ComponentProps<typeof MessageScroller> & {
  autoScroll?: boolean;
};

export function Conversation({
  className,
  children,
  autoScroll = true,
  ...props
}: ConversationProps) {
  return (
    <MessageScrollerProvider autoScroll={autoScroll}>
      <MessageScroller className={cn("min-h-0 flex-1", className)} {...props}>
        {children}
      </MessageScroller>
    </MessageScrollerProvider>
  );
}

export type ConversationContentProps = ComponentProps<typeof MessageScrollerContent>;

export function ConversationContent({ className, ...props }: ConversationContentProps) {
  return (
    <MessageScrollerViewport>
      <MessageScrollerContent className={cn("gap-6 p-4", className)} {...props} />
    </MessageScrollerViewport>
  );
}

export type ConversationEmptyStateProps = ComponentProps<"div"> & {
  title?: string;
  description?: string;
  icon?: ReactNode;
};

export function ConversationEmptyState({
  className,
  title = "No messages yet",
  description = "Start a conversation to see messages here",
  icon,
  children,
  ...props
}: ConversationEmptyStateProps) {
  return (
    <div
      className={cn(
        "flex size-full flex-col items-center justify-center gap-3 p-8 text-center",
        className,
      )}
      {...props}
    >
      {children ?? (
        <>
          {icon ? <div className="text-muted-foreground">{icon}</div> : null}
          <p className="text-sm font-medium text-foreground">{title}</p>
          {description ? (
            <p className="max-w-sm text-xs text-muted-foreground">{description}</p>
          ) : null}
        </>
      )}
    </div>
  );
}

export type ConversationScrollButtonProps = ComponentProps<typeof MessageScrollerButton>;

export function ConversationScrollButton(props: ConversationScrollButtonProps) {
  return <MessageScrollerButton {...props} />;
}
