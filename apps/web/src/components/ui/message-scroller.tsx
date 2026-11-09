"use client";

import { ArrowDownIcon } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type MessageScrollerContextValue = {
  autoScroll: boolean;
  viewportRef: React.RefObject<HTMLDivElement | null>;
  isAtEnd: boolean;
  setIsAtEnd: (value: boolean) => void;
  scrollToEnd: () => void;
  scrollToMessage: (messageId: string) => void;
  registerItem: (messageId: string, el: HTMLElement | null, scrollAnchor: boolean) => void;
  following: boolean;
  setFollowing: (value: boolean) => void;
};

const MessageScrollerContext = React.createContext<MessageScrollerContextValue | null>(null);

export function useMessageScroller() {
  const ctx = React.useContext(MessageScrollerContext);
  if (!ctx) {
    throw new Error("useMessageScroller must be used within MessageScrollerProvider");
  }
  return ctx;
}

export function MessageScrollerProvider({
  autoScroll = false,
  children,
}: {
  autoScroll?: boolean;
  children: React.ReactNode;
}) {
  const viewportRef = React.useRef<HTMLDivElement | null>(null);
  const itemsRef = React.useRef(
    new Map<string, { el: HTMLElement; scrollAnchor: boolean }>(),
  );
  const [isAtEnd, setIsAtEnd] = React.useState(true);
  const [following, setFollowing] = React.useState(true);
  const lastAnchorIdRef = React.useRef<string | null>(null);

  const scrollToEnd = React.useCallback(() => {
    const vp = viewportRef.current;
    if (!vp) return;
    vp.scrollTo({ top: vp.scrollHeight, behavior: "smooth" });
    setIsAtEnd(true);
    setFollowing(true);
  }, []);

  const scrollToMessage = React.useCallback((messageId: string) => {
    const item = itemsRef.current.get(messageId);
    const vp = viewportRef.current;
    if (!item || !vp) return;
    const top = item.el.offsetTop - 16;
    vp.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }, []);

  const registerItem = React.useCallback(
    (messageId: string, el: HTMLElement | null, scrollAnchor: boolean) => {
      if (!el) {
        itemsRef.current.delete(messageId);
        return;
      }
      itemsRef.current.set(messageId, { el, scrollAnchor });
      if (scrollAnchor && lastAnchorIdRef.current !== messageId) {
        lastAnchorIdRef.current = messageId;
        // Anchor the person's turn near the top so the reply streams under it.
        requestAnimationFrame(() => {
          const vp = viewportRef.current;
          if (!vp) return;
          const top = el.offsetTop - 12;
          vp.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
          setFollowing(true);
        });
      }
    },
    [],
  );

  const value = React.useMemo(
    () => ({
      autoScroll,
      viewportRef,
      isAtEnd,
      setIsAtEnd,
      scrollToEnd,
      scrollToMessage,
      registerItem,
      following,
      setFollowing,
    }),
    [autoScroll, isAtEnd, scrollToEnd, scrollToMessage, registerItem, following],
  );

  return (
    <MessageScrollerContext.Provider value={value}>
      {children}
    </MessageScrollerContext.Provider>
  );
}

export function MessageScroller({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="message-scroller"
      className={cn(
        "group/message-scroller relative flex size-full min-h-0 flex-col overflow-hidden",
        className,
      )}
      {...props}
    />
  );
}

export function MessageScrollerViewport({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const { viewportRef, setIsAtEnd, setFollowing, autoScroll, following } =
    useMessageScroller();

  React.useEffect(() => {
    const vp = viewportRef.current;
    if (!vp) return;

    const onScroll = () => {
      const distance = vp.scrollHeight - vp.scrollTop - vp.clientHeight;
      const atEnd = distance < 24;
      setIsAtEnd(atEnd);
      if (!atEnd) setFollowing(false);
      else if (autoScroll) setFollowing(true);
    };

    vp.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => vp.removeEventListener("scroll", onScroll);
  }, [viewportRef, setIsAtEnd, setFollowing, autoScroll]);

  React.useEffect(() => {
    if (!autoScroll || !following) return;
    const vp = viewportRef.current;
    if (!vp) return;
    vp.scrollTop = vp.scrollHeight;
  });

  return (
    <div
      ref={viewportRef}
      data-slot="message-scroller-viewport"
      role="region"
      aria-label="Conversation"
      className={cn(
        "cn-thin-scroll size-full min-h-0 min-w-0 overflow-y-auto overscroll-contain",
        className,
      )}
      {...props}
    />
  );
}

export function MessageScrollerContent({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="message-scroller-content"
      className={cn("flex h-max min-h-full flex-col gap-6", className)}
      {...props}
    />
  );
}

export function MessageScrollerItem({
  className,
  messageId,
  scrollAnchor = false,
  ...props
}: React.ComponentProps<"div"> & {
  messageId: string;
  scrollAnchor?: boolean;
}) {
  const { registerItem } = useMessageScroller();
  const ref = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    registerItem(messageId, ref.current, scrollAnchor);
    return () => registerItem(messageId, null, scrollAnchor);
  }, [messageId, scrollAnchor, registerItem]);

  return (
    <div
      ref={ref}
      data-slot="message-scroller-item"
      data-message-id={messageId}
      data-scroll-anchor={scrollAnchor || undefined}
      className={cn("min-w-0 shrink-0", className)}
      {...props}
    />
  );
}

export function MessageScrollerButton({
  className,
  direction = "end",
  ...props
}: React.ComponentProps<typeof Button> & {
  direction?: "end" | "start";
}) {
  const { isAtEnd, scrollToEnd, viewportRef } = useMessageScroller();
  const active = direction === "end" ? !isAtEnd : true;

  if (direction === "start") {
    return (
      <Button
        type="button"
        size="icon"
        variant="secondary"
        data-active={active}
        data-direction={direction}
        className={cn(
          "absolute left-1/2 top-4 z-10 -translate-x-1/2 rounded-full border border-border bg-background",
          !active && "pointer-events-none opacity-0",
          className,
        )}
        onClick={() => {
          viewportRef.current?.scrollTo({ top: 0, behavior: "smooth" });
        }}
        {...props}
      >
        <ArrowDownIcon className="h-4 w-4 rotate-180" />
        <span className="sr-only">Scroll to start</span>
      </Button>
    );
  }

  return (
    <Button
      type="button"
      size="icon"
      variant="secondary"
      data-active={active}
      data-direction={direction}
      className={cn(
        "absolute bottom-4 left-1/2 z-10 -translate-x-1/2 rounded-full border border-border bg-background transition-opacity",
        !active && "pointer-events-none scale-95 opacity-0",
        className,
      )}
      onClick={scrollToEnd}
      {...props}
    >
      <ArrowDownIcon className="h-4 w-4" />
      <span className="sr-only">Scroll to end</span>
    </Button>
  );
}
