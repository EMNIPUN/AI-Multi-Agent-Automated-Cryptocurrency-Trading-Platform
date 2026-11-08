"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { BlurFade } from "@/components/magicui/blur-fade";
import { Particles } from "@/components/magicui/particles";
import { GradientHeading } from "@/components/magicui/text-animate";
import { Button } from "@/components/ui/button";

export function LandingHero() {
  return (
    <section className="relative overflow-hidden px-4 pb-20 pt-20 md:px-6 md:pb-28 md:pt-28">
      <Particles className="opacity-70" quantity={90} />
      <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-[55%] horizon-glow" />

      <div className="relative z-10 mx-auto flex max-w-3xl flex-col items-center text-center">
        <BlurFade>
          <Link href="#features" className="badge-intro">
            <span aria-hidden>✨</span>
            Introducing multi-agent trading
            <ArrowRight className="h-3.5 w-3.5 opacity-70" />
          </Link>
        </BlurFade>

        <BlurFade delay={0.08}>
          <GradientHeading className="mt-8 text-4xl leading-[1.08] md:text-6xl lg:text-7xl">
            CryptoNova is the new way to trade with AI agents.
          </GradientHeading>
        </BlurFade>

        <BlurFade delay={0.14}>
          <p className="mt-6 max-w-xl text-base text-white/55 md:text-lg">
            Beautifully designed monitoring, paper execution, and risk guards — so you can
            practice with confidence before live trading ever unlocks.
          </p>
        </BlurFade>

        <BlurFade delay={0.2}>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Button asChild size="lg" className="rounded-full px-7">
              <Link href="/signup">
                Get Started for free
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="rounded-full border-white/15">
              <a href="#features">See features</a>
            </Button>
          </div>
        </BlurFade>
      </div>
    </section>
  );
}
