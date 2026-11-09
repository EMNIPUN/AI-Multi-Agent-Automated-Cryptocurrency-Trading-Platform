import type { ReactNode } from "react";

import { BorderBeam } from "@/components/magicui/border-beam";
import { cn } from "@/lib/utils";

export function SectionPanel({
  title,
  description,
  actions,
  children,
  beam,
  className,
  bodyClassName,
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  beam?: boolean;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("cn-panel flex flex-col p-5 md:p-6", className)}>
      {beam ? <BorderBeam size={200} duration={14} colorFrom="#F7A600" colorTo="#FFCE6E" /> : null}
      {(title || actions) && (
        <div className="relative z-10 mb-4 flex shrink-0 flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title ? (
              <h2 className="text-base font-medium tracking-tight text-foreground md:text-lg">{title}</h2>
            ) : null}
            {description ? (
              <p className="mt-1 text-sm text-muted-foreground">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
        </div>
      )}
      <div className={cn("relative z-10 min-h-0 flex-1", bodyClassName)}>{children}</div>
    </section>
  );
}
