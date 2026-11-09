"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

/** Magic UI–style meteor shower for hero atmosphere. */
export function Meteors({ number = 18, className }: { number?: number; className?: string }) {
  const [styles, setStyles] = useState<React.CSSProperties[]>([]);

  useEffect(() => {
    setStyles(
      Array.from({ length: number }).map(() => ({
        top: "-5%",
        left: `${Math.floor(Math.random() * 100)}%`,
        animationDelay: `${Math.random() * 1.2 + 0.2}s`,
        animationDuration: `${Math.floor(Math.random() * 8 + 4)}s`,
      })),
    );
  }, [number]);

  return (
    <div className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)} aria-hidden>
      {styles.map((style, i) => (
        <span
          key={i}
          style={style}
          className="absolute h-0.5 w-0.5 rotate-[215deg] animate-meteor rounded-full bg-orange-300 shadow-[0_0_0_1px_#ffffff10]"
        >
          <span className="pointer-events-none absolute top-1/2 -z-10 h-px w-[50px] -translate-y-1/2 bg-gradient-to-r from-orange-400 to-transparent" />
        </span>
      ))}
    </div>
  );
}
