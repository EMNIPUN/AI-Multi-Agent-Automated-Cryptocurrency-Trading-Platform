import { cn } from "@/lib/utils";

/** Startup-template metallic headline gradient (white → soft fade). */
export function GradientHeading({
  children,
  className,
  as: Tag = "h1",
}: {
  children: React.ReactNode;
  className?: string;
  as?: "h1" | "h2" | "h3" | "p";
}) {
  return (
    <Tag
      className={cn(
        "bg-gradient-to-b from-white from-30% to-white/40 bg-clip-text font-medium tracking-tight text-transparent",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
