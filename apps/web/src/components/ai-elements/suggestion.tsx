"use client";

import type { ComponentProps } from "react";
import { useCallback } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type SuggestionsProps = ComponentProps<"div">;

/** AI Elements Suggestions — horizontal chip row (scrolls sideways). */
export function Suggestions({ className, children, ...props }: SuggestionsProps) {
  return (
    <div
      className={cn(
        "flex gap-2 overflow-x-auto overscroll-x-contain scrollbar-none",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export type SuggestionProps = Omit<ComponentProps<typeof Button>, "onClick"> & {
  suggestion: string;
  onClick?: (suggestion: string) => void;
};

export function Suggestion({
  suggestion,
  onClick,
  className,
  variant = "outline",
  size = "sm",
  children,
  ...props
}: SuggestionProps) {
  const handleClick = useCallback(() => {
    onClick?.(suggestion);
  }, [onClick, suggestion]);

  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      className={cn("shrink-0 cursor-pointer rounded-full px-4", className)}
      onClick={handleClick}
      {...props}
    >
      {children || suggestion}
    </Button>
  );
}
