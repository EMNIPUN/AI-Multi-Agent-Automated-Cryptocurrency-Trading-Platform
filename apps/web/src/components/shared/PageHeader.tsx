"use client";

import { BlurFade } from "@/components/magicui/blur-fade";

export function PageHeader({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <BlurFade>
      <header className="mb-6">
        <p className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.16em] text-amber-200/70">
          CryptoNova
        </p>
        <h1 className="text-metallic text-2xl font-medium tracking-tight md:text-3xl">{title}</h1>
        {description ? (
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            {description}
          </p>
        ) : null}
      </header>
    </BlurFade>
  );
}
