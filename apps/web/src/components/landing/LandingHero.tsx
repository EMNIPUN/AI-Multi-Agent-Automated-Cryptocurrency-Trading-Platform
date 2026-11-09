"use client";

import Link from "next/link";
import { ArrowRight, Layers3 } from "lucide-react";

import { BlurFade } from "@/components/magicui/blur-fade";
import { Button } from "@/components/ui/button";

export function LandingHero() {
  return (
    <section className="relative overflow-hidden px-4 pb-20 pt-20 md:px-6 md:pb-28 md:pt-28">
      <div aria-hidden className="pointer-events-none absolute inset-0 sky-hero-glow" />

      <div className="relative z-10 mx-auto flex max-w-3xl flex-col items-center text-center">
        <BlurFade>
          <Link
            href="#features"
            className="badge-intro gap-2 text-[13px] transition-colors hover:border-brand/40 hover:text-foreground"
          >
            <Layers3 className="h-3.5 w-3.5 text-brand" />
            Introducing multi-agent trading automations
            <ArrowRight className="h-3.5 w-3.5 opacity-40" />
          </Link>
        </BlurFade>

        <BlurFade delay={0.08}>
          <h1 className="mt-8 text-balance text-4xl font-semibold leading-[1.05] tracking-tight text-foreground sm:text-5xl md:text-6xl lg:text-[4.35rem]">
            Meet your AI Agent
            <br />
            Streamline your trading
          </h1>
        </BlurFade>

        <BlurFade delay={0.14}>
          <p className="mt-6 max-w-xl text-pretty text-base leading-relaxed text-muted-foreground md:text-lg">
            CryptoNova coordinates research, risk, and paper execution so you can focus on edge —
            not busywork. Live trading stays locked until you intentionally unlock it.
          </p>
        </BlurFade>

        <BlurFade delay={0.2}>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Button asChild size="lg" className="rounded-full px-7">
              <Link href="/signup">
                Try for Free
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="rounded-full">
              <Link href="/login">Log in</Link>
            </Button>
          </div>
        </BlurFade>
      </div>

      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-[48%] horizon-glow opacity-95"
      />
    </section>
  );
}
