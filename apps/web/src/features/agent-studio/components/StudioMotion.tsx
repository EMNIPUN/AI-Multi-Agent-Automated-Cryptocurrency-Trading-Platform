"use client";

import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/utils";

import { studioFade, studioSoftSpring, studioStagger } from "../lib/motion-tokens";

/** Ambient studio atmosphere — transform/opacity only, no fake trading motion. */
export function StudioAtmosphere({ className }: { className?: string }) {
  const reduce = useReducedMotion();
  if (reduce) {
    return (
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,hsl(var(--surface-glow-a)/0.18),transparent_55%),radial-gradient(ellipse_at_bottom_right,hsl(var(--surface-glow-b)/0.14),transparent_50%)]",
          className,
        )}
      />
    );
  }
  return (
    <div aria-hidden className={cn("pointer-events-none absolute inset-0 -z-10 overflow-hidden", className)}>
      <motion.div
        className="absolute -left-24 top-0 h-72 w-72 rounded-full bg-[hsl(var(--surface-glow-a)/0.22)] blur-3xl"
        animate={{ x: [0, 24, 0], y: [0, 12, 0], opacity: [0.35, 0.55, 0.35] }}
        transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute -right-16 top-24 h-80 w-80 rounded-full bg-[hsl(var(--surface-glow-b)/0.18)] blur-3xl"
        animate={{ x: [0, -18, 0], y: [0, 20, 0], opacity: [0.28, 0.45, 0.28] }}
        transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
      />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,transparent_20%,hsl(var(--background)/0.55)_80%)]" />
    </div>
  );
}

export function StudioReveal({
  children,
  className,
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...studioSoftSpring, delay }}
    >
      {children}
    </motion.div>
  );
}

export function StudioStagger({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="show"
      variants={{
        hidden: {},
        show: studioStagger,
      }}
    >
      {children}
    </motion.div>
  );
}

export function StudioStaggerItem({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      variants={{
        hidden: { opacity: 0, y: 12 },
        show: { opacity: 1, y: 0, transition: studioFade },
      }}
    >
      {children}
    </motion.div>
  );
}
