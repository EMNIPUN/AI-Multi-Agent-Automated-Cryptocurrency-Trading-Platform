import type { ReactNode } from "react";

import { BlurFade } from "@/components/magicui/blur-fade";
import { ModeBadge, type ModeKind } from "@/components/command-center/ModeBadge";
import { cn } from "@/lib/utils";

export function PageFrame({
  eyebrow = "CryptoNova",
  title,
  description,
  modes = ["readonly", "live"],
  actions,
  children,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  modes?: ModeKind[];
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex w-full min-h-0 min-w-0 max-w-full flex-col space-y-5 pb-8", className)}>
      <BlurFade className="shrink-0">
        <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0 max-w-3xl">
            <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-brand">
              {eyebrow}
            </p>
            <div className="mt-0.5 flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-medium tracking-tight text-foreground md:text-xl">
                {title}
              </h1>
              {modes.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {modes.map((m) => (
                    <ModeBadge key={m} mode={m} />
                  ))}
                </div>
              ) : null}
            </div>
            {description ? (
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
        </header>
      </BlurFade>
      {children}
    </div>
  );
}
