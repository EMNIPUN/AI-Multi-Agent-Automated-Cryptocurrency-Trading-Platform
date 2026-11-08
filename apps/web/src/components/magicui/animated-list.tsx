"use client";

import React, {
  useEffect,
  useMemo,
  useState,
  type ComponentPropsWithoutRef,
} from "react";
import { AnimatePresence, motion, useReducedMotion, type MotionProps } from "motion/react";

import { cn } from "@/lib/utils";

export function AnimatedListItem({ children }: { children: React.ReactNode }) {
  const animations: MotionProps = {
    initial: { scale: 0, opacity: 0 },
    animate: { scale: 1, opacity: 1, originY: 0 },
    exit: { scale: 0, opacity: 0 },
    transition: { type: "spring", stiffness: 350, damping: 40 },
  };

  return (
    <motion.div {...animations} layout className="mx-auto w-full">
      {children}
    </motion.div>
  );
}

export interface AnimatedListProps extends ComponentPropsWithoutRef<"div"> {
  children: React.ReactNode;
  /** Delay between revealing items (Magic UI sequential mode). Set 0 for instant stagger. */
  delay?: number;
}

/** Magic UI Animated List — reveals items in sequence (or soft stagger when delay=0). */
export const AnimatedList = React.memo(
  ({ children, className, delay = 0, ...props }: AnimatedListProps) => {
    const reduce = useReducedMotion();
    const childrenArray = useMemo(() => React.Children.toArray(children), [children]);
    const [index, setIndex] = useState(delay > 0 ? 0 : childrenArray.length - 1);

    useEffect(() => {
      if (delay <= 0 || reduce) {
        setIndex(childrenArray.length - 1);
        return;
      }
      setIndex(0);
    }, [childrenArray.length, delay, reduce]);

    useEffect(() => {
      if (delay <= 0 || reduce) return;
      if (index >= childrenArray.length - 1) return;
      const timeout = setTimeout(() => setIndex((prev) => prev + 1), delay);
      return () => clearTimeout(timeout);
    }, [index, delay, childrenArray.length, reduce]);

    if (reduce || delay <= 0) {
      return (
        <div className={cn("flex flex-col gap-3", className)} {...props}>
          {childrenArray.map((child, i) => (
            <motion.div
              key={(child as React.ReactElement)?.key ?? i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: i * 0.03 }}
            >
              {child}
            </motion.div>
          ))}
        </div>
      );
    }

    const itemsToShow = childrenArray.slice(0, index + 1).reverse();

    return (
      <div className={cn("flex flex-col items-center gap-3", className)} {...props}>
        <AnimatePresence>
          {itemsToShow.map((item) => (
            <AnimatedListItem key={(item as React.ReactElement).key}>
              {item}
            </AnimatedListItem>
          ))}
        </AnimatePresence>
      </div>
    );
  },
);

AnimatedList.displayName = "AnimatedList";
