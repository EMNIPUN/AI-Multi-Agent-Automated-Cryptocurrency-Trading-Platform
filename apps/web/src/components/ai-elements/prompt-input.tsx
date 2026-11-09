"use client";

import { CornerDownLeftIcon, SquareIcon } from "lucide-react";
import {
  useCallback,
  useState,
  type ComponentProps,
  type FormEvent,
  type FormEventHandler,
  type HTMLAttributes,
  type KeyboardEventHandler,
} from "react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

export type ChatStatus = "ready" | "submitted" | "streaming" | "error";

export interface PromptInputMessage {
  text: string;
  files: never[];
}

export type PromptInputProps = Omit<HTMLAttributes<HTMLFormElement>, "onSubmit"> & {
  onSubmit: (
    message: PromptInputMessage,
    event: FormEvent<HTMLFormElement>,
  ) => void | Promise<void>;
};

/** AI Elements PromptInput — compact composer form (text-only for Orchestrator). */
export function PromptInput({ className, onSubmit, children, ...props }: PromptInputProps) {
  const handleSubmit: FormEventHandler<HTMLFormElement> = useCallback(
    async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const formData = new FormData(form);
      const text = String(formData.get("message") || "").trim();
      if (!text) return;
      try {
        await onSubmit({ text, files: [] }, event);
        form.reset();
      } catch {
        /* keep draft on error */
      }
    },
    [onSubmit],
  );

  return (
    <form className={cn("w-full", className)} onSubmit={handleSubmit} {...props}>
      {children}
    </form>
  );
}

export type PromptInputBodyProps = HTMLAttributes<HTMLDivElement>;

export function PromptInputBody({ className, ...props }: PromptInputBodyProps) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-2xl border border-border bg-card shadow-sm",
        className,
      )}
      {...props}
    />
  );
}

export type PromptInputTextareaProps = ComponentProps<"textarea">;

export function PromptInputTextarea({
  className,
  onKeyDown,
  placeholder = "What would you like to know?",
  ...props
}: PromptInputTextareaProps) {
  const [isComposing, setIsComposing] = useState(false);

  const handleKeyDown: KeyboardEventHandler<HTMLTextAreaElement> = useCallback(
    (e) => {
      onKeyDown?.(e);
      if (e.defaultPrevented) return;
      if (e.key !== "Enter") return;
      if (isComposing || e.nativeEvent.isComposing) return;
      if (e.shiftKey) return;
      // Prefer Cmd/Ctrl+Enter for multi-line; also allow plain Enter to submit
      if (!(e.metaKey || e.ctrlKey) && e.key === "Enter") {
        // Allow Enter alone to submit for chat UX
      }
      e.preventDefault();
      const { form } = e.currentTarget;
      const submitButton = form?.querySelector(
        'button[type="submit"]',
      ) as HTMLButtonElement | null;
      if (submitButton?.disabled) return;
      form?.requestSubmit();
    },
    [onKeyDown, isComposing],
  );

  return (
    <textarea
      name="message"
      rows={3}
      placeholder={placeholder}
      className={cn(
        "cn-thin-scroll field-sizing-content max-h-48 min-h-16 w-full resize-none bg-transparent px-4 pt-3 text-sm leading-relaxed text-foreground outline-none placeholder:text-muted-foreground",
        className,
      )}
      onCompositionStart={() => setIsComposing(true)}
      onCompositionEnd={() => setIsComposing(false)}
      onKeyDown={handleKeyDown}
      {...props}
    />
  );
}

export type PromptInputFooterProps = HTMLAttributes<HTMLDivElement>;

export function PromptInputFooter({ className, ...props }: PromptInputFooterProps) {
  return (
    <div
      className={cn("flex items-center justify-between gap-2 px-3 pb-3 pt-1", className)}
      {...props}
    />
  );
}

export type PromptInputToolsProps = HTMLAttributes<HTMLDivElement>;

export function PromptInputTools({ className, ...props }: PromptInputToolsProps) {
  return <div className={cn("flex min-w-0 items-center gap-1", className)} {...props} />;
}

export type PromptInputSubmitProps = ComponentProps<typeof Button> & {
  status?: ChatStatus;
  onStop?: () => void;
};

export function PromptInputSubmit({
  className,
  variant = "default",
  size = "icon",
  status = "ready",
  onStop,
  onClick,
  children,
  ...props
}: PromptInputSubmitProps) {
  const isGenerating = status === "submitted" || status === "streaming";

  return (
    <Button
      type={isGenerating && onStop ? "button" : "submit"}
      variant={variant}
      size={size}
      aria-label={isGenerating ? "Stop" : "Submit"}
      className={cn("rounded-full", className)}
      onClick={(e) => {
        if (isGenerating && onStop) {
          e.preventDefault();
          onStop();
          return;
        }
        onClick?.(e);
      }}
      {...props}
    >
      {children ??
        (status === "submitted" ? (
          <Spinner className="size-4" />
        ) : status === "streaming" ? (
          <SquareIcon className="h-3.5 w-3.5" />
        ) : (
          <CornerDownLeftIcon className="h-4 w-4" />
        ))}
    </Button>
  );
}
