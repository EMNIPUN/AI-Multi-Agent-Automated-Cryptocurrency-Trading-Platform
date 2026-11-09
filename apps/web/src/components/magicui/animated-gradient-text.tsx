import { cn } from "@/lib/utils";

/** Magic UI–style animated gradient text / badge. */
export function AnimatedGradientText({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "group relative mx-auto flex max-w-fit flex-row items-center justify-center rounded-full bg-muted/40 px-4 py-1.5 text-sm font-medium shadow-[inset_0_-8px_10px_#8fdfff1f] backdrop-blur-sm transition-shadow duration-500 ease-out [--bg-size:300%] hover:shadow-[inset_0_-5px_10px_#8fdfff3f]",
        className,
      )}
    >
      <div
        className={cn(
          "absolute inset-0 block h-full w-full animate-aurora-border rounded-[inherit] bg-gradient-to-r from-[#F7A600]/55 via-[#FFCE6E]/50 to-[#F7A600]/45 bg-[length:var(--bg-size)_100%] p-[1px] ![mask-composite:subtract] [mask:linear-gradient(#fff_0_0)_content-box,linear-gradient(#fff_0_0)]",
        )}
      />
      {children}
    </div>
  );
}
