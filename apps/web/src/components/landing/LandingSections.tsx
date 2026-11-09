"use client";

import Link from "next/link";
import { Check, ChevronDown, ArrowRight } from "lucide-react";
import { useState } from "react";

import { BorderBeam } from "@/components/magicui/border-beam";
import { BlurFade } from "@/components/magicui/blur-fade";
import { Marquee } from "@/components/magicui/marquee";
import { NumberTicker } from "@/components/magicui/number-ticker";
import { Button } from "@/components/ui/button";
import {
  FAQS,
  FEATURES,
  PRICING,
  STEPS,
  TESTIMONIALS,
  TRUST_LOGOS,
} from "@/components/landing/landing-data";
import { cn } from "@/lib/utils";

export function LogoCloud() {
  return (
    <section className="border-y border-border/50 py-10">
      <h2 className="mb-6 text-center text-xs font-medium uppercase tracking-[0.22em] text-foreground">
        Trusted by desks shipping trading systems
      </h2>
      <div className="relative mx-auto max-w-5xl">
        <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-24 bg-gradient-to-r from-background to-transparent" />
        <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-24 bg-gradient-to-l from-background to-transparent" />
        <Marquee pauseOnHover className="[--duration:28s]">
          {TRUST_LOGOS.map((name) => (
            <span
              key={name}
              className="mx-6 font-display text-lg tracking-tight text-muted-foreground/70"
            >
              {name}
            </span>
          ))}
        </Marquee>
      </div>
    </section>
  );
}

export function FeatureShowcase() {
  return (
    <section id="features" className="scroll-mt-24 px-4 py-20 md:px-6 md:py-28">
      <div className="mx-auto max-w-6xl">
        <BlurFade>
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-metallic text-3xl font-medium tracking-tight md:text-4xl">
              Empower your desk with AI
            </h2>
            <p className="mt-3 text-muted-foreground">
              Ask CryptoNova for real-time agent collaboration, risk gates, and actionable thesis
              context — so you can streamline the loop without live-order risk.
            </p>
          </div>
        </BlurFade>

        <div className="mt-14 space-y-16">
          {FEATURES.map((feature, i) => (
            <BlurFade key={feature.id} delay={0.05 * i}>
              <div
                className={cn(
                  "grid items-center gap-8 lg:grid-cols-2",
                  i % 2 === 1 && "lg:[&>*:first-child]:order-2",
                )}
              >
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-orange-300/80">
                    0{i + 1} · Feature
                  </p>
                  <h3 className="mt-2 font-display text-2xl tracking-tight md:text-3xl">
                    {feature.title}
                  </h3>
                  <p className="mt-3 text-muted-foreground">{feature.body}</p>
                  <ul className="mt-5 space-y-2">
                    {feature.points.map((point) => (
                      <li key={point} className="flex items-start gap-2 text-sm">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-foreground" />
                        <span>{point}</span>
                      </li>
                    ))}
                  </ul>
                  <Button asChild variant="outline" className="mt-6 rounded-full">
                    <Link href="/signup">
                      Learn more
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </Button>
                </div>
                <div className="relative overflow-hidden rounded-2xl border border-border/70 bg-card/60 p-5 backdrop-blur-xl">
                  <BorderBeam
                    size={160}
                    duration={9}
                    colorFrom="#F7A600"
                    colorTo={i === 1 ? "#FFCE6E" : "#F7A600"}
                  />
                  <div className="space-y-3 font-mono text-xs text-muted-foreground">
                    <div className="rounded-lg border border-border/60 bg-background/70 p-3">
                      <p className="text-foreground">agent.research → thesis</p>
                      <p className="mt-1">BTCUSDT bias: trend_continuation</p>
                    </div>
                    <div className="rounded-lg border border-border/60 bg-background/70 p-3">
                      <p className="text-warning">agent.risk → gate</p>
                      <p className="mt-1">max_dd 2.1% · size capped · ok</p>
                    </div>
                    <div className="rounded-lg border border-border/60 bg-background/70 p-3">
                      <p className="text-profit">agent.execution → paper</p>
                      <p className="mt-1">queued · SAMPLE-safe · no live route</p>
                    </div>
                  </div>
                </div>
              </div>
            </BlurFade>
          ))}
        </div>
      </div>
    </section>
  );
}

export function StatsBand() {
  return (
    <section className="border-y border-border/50 bg-card/30 px-4 py-16 md:px-6">
      <div className="mx-auto grid max-w-5xl gap-10 text-center sm:grid-cols-3">
        <BlurFade>
          <p className="text-metallic text-4xl font-medium tracking-tight text-foreground">
            <NumberTicker value={120} decimalPlaces={0} />+
          </p>
          <p className="mt-2 text-sm text-muted-foreground">Markets watched in public streams</p>
        </BlurFade>
        <BlurFade delay={0.08}>
          <p className="text-metallic text-4xl font-medium tracking-tight text-emerald-300">
            <NumberTicker value={3} decimalPlaces={0} />
          </p>
          <p className="mt-2 text-sm text-muted-foreground">Specialist agents per trading loop</p>
        </BlurFade>
        <BlurFade delay={0.14}>
          <p className="text-metallic text-4xl font-medium tracking-tight text-orange-300">0</p>
          <p className="mt-2 text-sm text-muted-foreground">Live orders until you unlock gates</p>
        </BlurFade>
      </div>
    </section>
  );
}

export function HowItWorks() {
  return (
    <section id="how-it-works" className="scroll-mt-24 px-4 py-20 md:px-6 md:py-28">
      <div className="mx-auto max-w-6xl">
        <BlurFade>
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-metallic text-3xl font-medium tracking-tight md:text-4xl">
              Setup. Connect. Paper. Ship.
            </h2>
            <p className="mt-3 text-muted-foreground">
              Collaborate with your agents using AI-powered tools — without enabling live trading by
              accident.
            </p>
          </div>
        </BlurFade>

        <div className="mt-14 grid gap-6 md:grid-cols-3">
          {STEPS.map((step, i) => (
            <BlurFade key={step.title} delay={0.06 * i}>
              <div className="relative h-full overflow-hidden rounded-2xl border border-border/70 bg-card/50 p-6">
                <p className="font-mono text-xs text-foreground">0{i + 1}</p>
                <h3 className="mt-3 font-display text-xl tracking-tight">{step.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{step.body}</p>
              </div>
            </BlurFade>
          ))}
        </div>
      </div>
    </section>
  );
}

function TestimonialCard({
  quote,
  name,
  role,
}: {
  quote: string;
  name: string;
  role: string;
}) {
  return (
    <figure className="relative w-80 overflow-hidden rounded-2xl border border-border/70 bg-card/60 p-5">
      <blockquote className="text-sm leading-relaxed text-foreground/90">&ldquo;{quote}&rdquo;</blockquote>
      <figcaption className="mt-4">
        <p className="text-sm font-medium">{name}</p>
        <p className="text-xs text-muted-foreground">{role}</p>
      </figcaption>
    </figure>
  );
}

export function Testimonials() {
  const rowA = TESTIMONIALS.slice(0, 3);
  const rowB = TESTIMONIALS.slice(3);

  return (
    <section className="px-4 py-20 md:px-6 md:py-28">
      <div className="mx-auto max-w-6xl">
        <BlurFade>
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-metallic text-3xl font-medium tracking-tight md:text-4xl">
              Hear from the operator community
            </h2>
            <p className="mt-3 text-muted-foreground">
              Desks use CryptoNova to accelerate research while keeping risk in the loop.
            </p>
          </div>
        </BlurFade>

        <div className="relative mt-12">
          <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-background to-transparent md:w-28" />
          <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-background to-transparent md:w-28" />
          <Marquee pauseOnHover className="[--duration:50s]">
            {rowA.map((t) => (
              <TestimonialCard key={t.name} {...t} />
            ))}
          </Marquee>
          <Marquee reverse pauseOnHover className="mt-4 [--duration:55s]">
            {rowB.map((t) => (
              <TestimonialCard key={t.name} {...t} />
            ))}
          </Marquee>
        </div>
      </div>
    </section>
  );
}

export function Pricing() {
  const [annual, setAnnual] = useState(false);

  return (
    <section id="pricing" className="scroll-mt-24 px-4 py-20 md:px-6 md:py-28">
      <div className="mx-auto max-w-6xl">
        <BlurFade>
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-metallic text-3xl font-medium tracking-tight md:text-4xl">
              Build more. Pay less. Scale smart.
            </h2>
            <p className="mt-3 text-muted-foreground">
              Start free on paper. Upgrade only when your agents prove value.
            </p>
            <div className="mt-6 inline-flex rounded-full border border-border/70 bg-card/50 p-1">
              <button
                type="button"
                onClick={() => setAnnual(false)}
                className={cn(
                  "rounded-full px-4 py-1.5 text-sm",
                  !annual ? "bg-primary text-primary-foreground" : "text-muted-foreground",
                )}
              >
                Monthly
              </button>
              <button
                type="button"
                onClick={() => setAnnual(true)}
                className={cn(
                  "rounded-full px-4 py-1.5 text-sm",
                  annual ? "bg-primary text-primary-foreground" : "text-muted-foreground",
                )}
              >
                Annually
              </button>
            </div>
          </div>
        </BlurFade>

        <div className="mt-12 grid gap-6 lg:grid-cols-3">
          {PRICING.map((plan, i) => {
            const price =
              plan.price === "Custom"
                ? "Custom"
                : plan.price === "$0"
                  ? "$0"
                  : annual
                    ? `$${Math.round(Number(plan.price.replace("$", "")) * 10)}`
                    : plan.price;
            const period =
              plan.price === "Custom" ? "" : annual && plan.price !== "$0" ? "/year" : plan.period;

            return (
              <BlurFade key={plan.name} delay={0.06 * i}>
                <div
                  className={cn(
                    "relative flex h-full flex-col overflow-hidden rounded-2xl border p-6",
                    plan.featured
                      ? "border-brand/40 bg-card shadow-[0_0_60px_-24px_hsl(var(--brand)/0.45)]"
                      : "border-border bg-card",
                  )}
                >
                  {plan.featured ? (
                    <BorderBeam size={180} duration={8} colorFrom="#F7A600" colorTo="#FFCE6E" />
                  ) : null}
                  {plan.featured ? (
                    <span className="mb-3 w-fit rounded-full border border-brand/40 bg-brand/15 px-2.5 py-0.5 text-[11px] font-medium text-foreground">
                      Popular
                    </span>
                  ) : null}
                  <h3 className="font-display text-xl tracking-tight">{plan.name}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{plan.blurb}</p>
                  <p className="mt-5 text-metallic text-4xl font-medium tracking-tight">
                    {price}
                    <span className="text-base text-muted-foreground">{period}</span>
                  </p>
                  <ul className="mt-6 flex-1 space-y-2">
                    {plan.perks.map((perk) => (
                      <li key={perk} className="flex gap-2 text-sm">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand" />
                        {perk}
                      </li>
                    ))}
                  </ul>
                  <Button
                    asChild
                    className="mt-8 rounded-full"
                    variant={plan.featured ? "default" : "outline"}
                  >
                    <Link href={plan.href}>{plan.cta}</Link>
                  </Button>
                </div>
              </BlurFade>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export function FAQ() {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <section id="faq" className="scroll-mt-24 px-4 py-20 md:px-6 md:py-28">
      <div className="mx-auto max-w-3xl">
        <BlurFade>
          <div className="text-center">
            <h2 className="text-metallic text-3xl font-medium tracking-tight md:text-4xl">
              Frequently asked questions
            </h2>
            <p className="mt-3 text-muted-foreground">
              Answers about CryptoNova, agents, and SAMPLE-safe defaults.
            </p>
          </div>
        </BlurFade>

        <div className="mt-10 divide-y divide-border/60 rounded-2xl border border-border/70 bg-card/40">
          {FAQS.map((item, i) => {
            const isOpen = open === i;
            return (
              <div key={item.q} className="px-5">
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-4 py-4 text-left"
                  aria-expanded={isOpen}
                  onClick={() => setOpen(isOpen ? null : i)}
                >
                  <span className="font-medium">{item.q}</span>
                  <ChevronDown
                    className={cn(
                      "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
                      isOpen && "rotate-180",
                    )}
                  />
                </button>
                {isOpen ? (
                  <p className="pb-4 text-sm leading-relaxed text-muted-foreground">{item.a}</p>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export function FinalCTA() {
  return (
    <section className="px-4 pb-20 md:px-6 md:pb-28">
      <BlurFade>
        <div className="relative mx-auto max-w-5xl overflow-hidden rounded-3xl border border-border bg-gradient-to-b from-muted via-card/60 to-background px-6 py-16 text-center md:px-12">
          <BorderBeam size={260} duration={12} colorFrom="#F7A600" colorTo="#FFCE6E" />
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,hsl(40_100%_48%_/_0.16),transparent_65%)]"
          />
          <h2 className="relative text-metallic text-3xl font-medium tracking-tight md:text-4xl">
            Ship your next trading loop with CryptoNova
          </h2>
          <p className="relative mx-auto mt-3 max-w-xl text-muted-foreground">
            Stop wiring dashboards by hand. Let agents handle research and risk — start paper
            trading smarter today, free.
          </p>
          <div className="relative mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild size="lg" className="rounded-full">
              <Link href="/signup">
                Start for free
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline" className="rounded-full">
              <a href="#features">Browse features</a>
            </Button>
          </div>
        </div>
      </BlurFade>
    </section>
  );
}

export function LandingFooter() {
  return (
    <footer className="border-t border-border/60 px-4 py-12 md:px-6">
      <div className="mx-auto grid max-w-6xl gap-10 md:grid-cols-4">
        <div className="md:col-span-1">
          <p className="font-display text-lg tracking-tight">CryptoNova</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Intelligent Trading. Disciplined Execution.
          </p>
        </div>
        {[
          {
            title: "Product",
            links: [
              { href: "#features", label: "Features" },
              { href: "#pricing", label: "Pricing" },
              { href: "/orchestrator", label: "Orchestrator" },
              { href: "/agents", label: "Agents" },
            ],
          },
          {
            title: "Account",
            links: [
              { href: "/login", label: "Sign in" },
              { href: "/signup", label: "Sign up" },
              { href: "/settings", label: "Settings" },
            ],
          },
          {
            title: "Platform",
            links: [
              { href: "#faq", label: "FAQ" },
              { href: "/paper", label: "Paper" },
              { href: "/risk", label: "Risk" },
              { href: "/markets", label: "Markets" },
            ],
          },
        ].map((col) => (
          <div key={col.title}>
            <p className="text-sm font-medium">{col.title}</p>
            <ul className="mt-3 space-y-2">
              {col.links.map((link) => (
                <li key={link.href}>
                  {link.href.startsWith("#") ? (
                    <a
                      href={link.href}
                      className="text-sm text-muted-foreground hover:text-foreground"
                    >
                      {link.label}
                    </a>
                  ) : (
                    <Link
                      href={link.href}
                      className="text-sm text-muted-foreground hover:text-foreground"
                    >
                      {link.label}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="mx-auto mt-10 max-w-6xl text-xs text-muted-foreground">
        © {new Date().getFullYear()} CryptoNova · public markets + gated private reads · trading off
      </p>
    </footer>
  );
}
