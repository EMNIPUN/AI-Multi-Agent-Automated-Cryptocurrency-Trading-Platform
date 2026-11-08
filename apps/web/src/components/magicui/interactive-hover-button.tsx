import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Hover CTA. Uses a scoped `group/ihb` and a clipped fill — never scale a
 * small dot by ~100× (that escaped overflow and painted a giant white circle
 * after tab clicks / sticky touch hover).
 */
export function InteractiveHoverButton({
  children,
  className,
  href,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { href?: string }) {
  const inner = (
    <>
      <span className="relative z-10 flex items-center justify-center gap-2 transition-all duration-300 [@media(hover:hover)]:group-hover/ihb:translate-x-8 [@media(hover:hover)]:group-hover/ihb:opacity-0">
        <span className="h-2 w-2 shrink-0 rounded-full bg-primary" aria-hidden />
        <span>{children}</span>
      </span>
      {/* Fill stays inside the button via overflow-hidden + isolate */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 z-0 origin-left scale-x-0 rounded-full bg-primary transition-transform duration-300 ease-out [@media(hover:hover)]:group-hover/ihb:scale-x-100"
      />
      <span className="absolute inset-0 z-10 flex items-center justify-center gap-2 text-primary-foreground opacity-0 transition-opacity duration-300 [@media(hover:hover)]:group-hover/ihb:opacity-100">
        <span>{children}</span>
        <ArrowRight className="h-4 w-4" />
      </span>
    </>
  );

  const classes = cn(
    "group/ihb relative isolate inline-flex w-auto cursor-pointer items-center justify-center overflow-hidden rounded-full border border-white/15 bg-background px-6 py-2 text-center text-sm font-semibold",
    className,
  );

  if (href) {
    return (
      <Link href={href} className={classes}>
        {inner}
      </Link>
    );
  }

  return (
    <button type="button" className={classes} {...props}>
      {inner}
    </button>
  );
}
