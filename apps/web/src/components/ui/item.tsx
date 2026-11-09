import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const itemVariants = cva(
  "flex w-full flex-wrap items-center rounded-xl border text-sm outline-none transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-transparent",
        outline: "border-border bg-card",
        muted: "border-transparent bg-muted/50",
      },
      size: {
        default: "gap-3 p-3",
        sm: "gap-2.5 px-3 py-2",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export function Item({
  className,
  variant,
  size,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof itemVariants>) {
  return (
    <div
      data-slot="item"
      className={cn(itemVariants({ variant, size }), className)}
      {...props}
    />
  );
}

export function ItemMedia({
  className,
  variant = "default",
  ...props
}: React.ComponentProps<"div"> & { variant?: "default" | "icon" }) {
  return (
    <div
      data-slot="item-media"
      className={cn(
        "flex shrink-0 items-center justify-center",
        variant === "icon" &&
          "size-8 rounded-lg border border-border bg-muted text-muted-foreground [&_svg]:size-4",
        className,
      )}
      {...props}
    />
  );
}

export function ItemContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="item-content"
      className={cn("flex min-w-0 flex-1 flex-col gap-0.5", className)}
      {...props}
    />
  );
}

export function ItemTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="item-title"
      className={cn("truncate font-medium leading-none text-foreground", className)}
      {...props}
    />
  );
}

export function ItemDescription({ className, ...props }: React.ComponentProps<"p">) {
  return (
    <p
      data-slot="item-description"
      className={cn("text-xs leading-snug text-muted-foreground", className)}
      {...props}
    />
  );
}

export function ItemActions({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="item-actions"
      className={cn("ml-auto flex shrink-0 items-center gap-2", className)}
      {...props}
    />
  );
}
