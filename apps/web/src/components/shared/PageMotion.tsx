"use client";

import { usePathname } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Soft page enter — keeps the app feeling responsive without flashy transitions. */
export function PageMotion({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const pathname = usePathname();
  const reduce = useReducedMotion();

  if (reduce) {
    return <div className={cn("min-w-0 w-full max-w-full", className)}>{children}</div>;
  }

  return (
    <motion.div
      key={pathname}
      className={cn("min-w-0 w-full max-w-full", className)}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.16, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}
