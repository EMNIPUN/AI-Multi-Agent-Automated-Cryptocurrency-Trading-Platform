import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/** shadcn Chat Bubble — speech/content surface inside a Message. */
export function BubbleGroup({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="bubble-group"
      className={cn("flex min-w-0 flex-col gap-2", className)}
      {...props}
    />
  );
}

const bubbleVariants = cva(
  "relative flex w-fit max-w-[min(100%,36rem)] min-w-0 flex-col",
  {
    variants: {
      variant: {
        default: "",
        secondary: "",
        muted: "",
        outline: "",
        ghost: "",
        destructive: "",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

const bubbleContentVariants = cva(
  "w-fit max-w-full min-w-0 overflow-hidden rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed break-words whitespace-pre-wrap",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        secondary: "bg-secondary text-secondary-foreground",
        muted: "bg-muted text-foreground",
        outline: "border border-border bg-card text-foreground shadow-sm",
        ghost: "bg-transparent p-0 text-foreground",
        destructive: "bg-destructive/10 text-destructive",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

const BubbleVariantContext = React.createContext<
  NonNullable<VariantProps<typeof bubbleContentVariants>["variant"]>
>("default");

export function Bubble({
  variant = "default",
  align = "start",
  className,
  children,
  ...props
}: React.ComponentProps<"div"> &
  VariantProps<typeof bubbleVariants> & {
    align?: "start" | "end";
  }) {
  return (
    <BubbleVariantContext.Provider value={variant ?? "default"}>
      <div
        data-slot="bubble"
        data-variant={variant}
        data-align={align}
        className={cn(
          bubbleVariants({ variant }),
          align === "end" && "ml-auto self-end",
          className,
        )}
        {...props}
      >
        {children}
      </div>
    </BubbleVariantContext.Provider>
  );
}

export function BubbleContent({ className, ...props }: React.ComponentProps<"div">) {
  const variant = React.useContext(BubbleVariantContext);
  return (
    <div
      data-slot="bubble-content"
      className={cn(bubbleContentVariants({ variant }), className)}
      {...props}
    />
  );
}
