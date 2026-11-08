"use client";

import Link from "next/link";
import {
  Activity,
  CandlestickChart,
  FlaskConical,
  ShieldCheck,
  Sparkles,
  Wallet,
} from "lucide-react";
import { useState } from "react";

import { NewsAlertStrip } from "@/components/news/NewsAlertStrip";
import { WalletBalancePanel } from "@/components/WalletBalancePanel";
import { DashboardMarkets } from "@/components/dashboard/DashboardMarkets";
import { AnimatedList } from "@/components/magicui/animated-list";
import { AvatarCircles } from "@/components/magicui/avatar-circles";
import { BentoCard, BentoGrid } from "@/components/magicui/bento-grid";
import { BlurFade } from "@/components/magicui/blur-fade";
import { BorderBeam } from "@/components/magicui/border-beam";
import { InteractiveHoverButton } from "@/components/magicui/interactive-hover-button";
import { NumberTicker } from "@/components/magicui/number-ticker";
import { Ripple } from "@/components/magicui/ripple";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { dashboardFixture } from "@/lib/fixtures/dashboard";
import { cn } from "@/lib/utils";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "practice", label: "Practice" },
  { id: "markets", label: "Markets" },
  { id: "agents", label: "Agents" },
  { id: "wallet", label: "Wallet" },
  { id: "activity", label: "Activity" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const AVATARS = [
  { imageUrl: "https://api.dicebear.com/9.x/shapes/svg?seed=nova1" },
  { imageUrl: "https://api.dicebear.com/9.x/shapes/svg?seed=nova2" },
  { imageUrl: "https://api.dicebear.com/9.x/shapes/svg?seed=nova3" },
  { imageUrl: "https://api.dicebear.com/9.x/shapes/svg?seed=nova4" },
];

const BENTO = [
  {
    name: "Markets",
    description: "Live public charts and tickers — no private keys required.",
    href: "/markets",
    cta: "Open charts",
    Icon: CandlestickChart,
    className: "lg:col-span-2",
    background: (
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(245,158,11,0.12),transparent_55%)]" />
    ),
  },
  {
    name: "Paper trade",
    description: "Practice safely with virtual money before going live.",
    href: "/paper",
    cta: "Start practice",
    Icon: FlaskConical,
    className: "lg:col-span-1",
    background: (
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_left,rgba(255,255,255,0.08),transparent_55%)]" />
    ),
  },
  {
    name: "AI agents",
    description: "Watch research, risk, and execution agents work together.",
    href: "/agents/live",
    cta: "Open studio",
    Icon: Activity,
    className: "lg:col-span-1",
    background: (
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(52,211,153,0.1),transparent_55%)]" />
    ),
  },
  {
    name: "Risk guard",
    description: "Stay protected with loss limits and trading locks.",
    href: "/risk",
    cta: "Review risk",
    Icon: ShieldCheck,
    className: "lg:col-span-2",
    background: (
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(255,255,255,0.06),transparent_60%)]" />
    ),
  },
] as const;

export function DashboardHome() {
  const f = dashboardFixture;
  const agentOk = f.agent.status !== "OFFLINE" && !f.agent.heartbeat_stale;
  const [tab, setTab] = useState<TabId>("overview");

  return (
    <div className="space-y-5 pb-8">
      <NewsAlertStrip />
      <BlurFade>
        <section className="relative overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] p-6 md:p-8">
          <BorderBeam size={280} duration={14} colorFrom="#f59e0b" colorTo="#ffffff" />
          <Ripple className="opacity-25" mainCircleSize={80} numCircles={4} />
          <div className="relative z-10 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-xl">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="badge-intro text-xs">
                  <Sparkles className="h-3 w-3" />
                  Demo mode
                </span>
                <Badge variant="outline" className="rounded-full border-white/15 text-white/70">
                  Live trading off
                </Badge>
              </div>
              <h1 className="text-metallic text-3xl font-medium tracking-tight md:text-4xl">
                Welcome back
              </h1>
              <p className="mt-2 text-sm leading-relaxed text-white/55 md:text-base">
                Use the tabs below to switch views in place — no scrolling around the page.
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <AvatarCircles avatarUrls={AVATARS} numPeople={12} />
                <p className="text-xs text-white/45">Operators exploring paper mode</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-3">
              <InteractiveHoverButton href="/paper">Start paper trade</InteractiveHoverButton>
              <InteractiveHoverButton href="/markets" className="border-white/20 bg-transparent">
                View markets
              </InteractiveHoverButton>
            </div>
          </div>
        </section>
      </BlurFade>

      <Separator className="bg-white/10" />

      <Tabs
        value={tab}
        onValueChange={(value) => setTab(value as TabId)}
        className="min-h-[28rem]"
      >
        <TabsList aria-label="Dashboard categories">
          {TABS.map((item) => (
            <TabsTrigger key={item.id} value={item.id}>
              {item.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <BlurFade>
            <BentoGrid className="auto-rows-[16rem]">
              {BENTO.map((card) => (
                <BentoCard
                  key={`${card.name}-${card.href}`}
                  name={card.name}
                  className={card.className}
                  background={card.background}
                  Icon={card.Icon}
                  description={card.description}
                  href={card.href}
                  cta={card.cta}
                />
              ))}
            </BentoGrid>
          </BlurFade>
        </TabsContent>

        <TabsContent value="practice" className="mt-4">
          <BlurFade>
            <section className="relative overflow-hidden rounded-3xl border border-white/15 bg-card/70 p-6 md:p-8">
              <BorderBeam size={200} duration={10} colorFrom="#f59e0b" colorTo="#ffffff" />
              <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-amber-200/80">
                Practice account
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Virtual money for learning — not your Bybit wallet
              </p>
              <p className="mt-5 text-4xl font-medium tracking-tight text-white md:text-5xl">
                $<NumberTicker value={f.paper.equity} decimalPlaces={2} />
              </p>
              <div className="mt-6 grid max-w-2xl grid-cols-3 gap-3">
                {[
                  { label: "Cash", value: f.paper.cash, tone: "text-foreground" },
                  { label: "Open P&L", value: f.paper.unrealized, tone: "text-profit" },
                  { label: "Closed P&L", value: f.paper.realized, tone: "text-loss" },
                ].map((m) => (
                  <div
                    key={m.label}
                    className="rounded-2xl border border-border/60 bg-background/50 p-3"
                  >
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                      {m.label}
                    </p>
                    <p className={cn("mt-1 font-mono text-sm md:text-base", m.tone)}>
                      {m.value >= 0 ? "" : "−"}
                      ${Math.abs(m.value).toFixed(2)}
                    </p>
                  </div>
                ))}
              </div>
              <div className="mt-6">
                <InteractiveHoverButton href="/paper">Open paper desk</InteractiveHoverButton>
              </div>
            </section>
          </BlurFade>
        </TabsContent>

        <TabsContent value="markets" className="mt-4">
          <BlurFade>
            <DashboardMarkets />
          </BlurFade>
        </TabsContent>

        <TabsContent value="agents" className="mt-4">
          <BlurFade>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="cn-glow-card p-5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Activity className="h-4 w-4 text-white/80" />
                    <h2 className="text-lg font-medium tracking-tight">AI agent</h2>
                  </div>
                  <Badge variant={agentOk ? "success" : "warning"} className="rounded-full">
                    {agentOk ? "Online" : "Resting"}
                  </Badge>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {agentOk
                    ? `Watching ${f.agent.symbol} on ${f.agent.interval}m · ${f.agent.strategy}`
                    : "Agents are paused right now. You can still browse markets and paper trade."}
                </p>
                <div className="mt-4">
                  <InteractiveHoverButton href="/agents/live">
                    Open agent studio
                  </InteractiveHoverButton>
                </div>
              </div>
              <div className="cn-glow-card p-5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-emerald-300" />
                    <h2 className="text-lg font-medium tracking-tight">Risk guard</h2>
                  </div>
                  <Badge variant="success" className="rounded-full">
                    Protected
                  </Badge>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  Daily loss guard set to {f.risk.daily_loss_limit}. Live orders stay blocked until
                  you unlock trading.
                </p>
                <div className="mt-4">
                  <InteractiveHoverButton href="/risk">Review risk</InteractiveHoverButton>
                </div>
              </div>
            </div>
          </BlurFade>
        </TabsContent>

        <TabsContent value="wallet" className="mt-4">
          <BlurFade>
            <WalletBalancePanel compact />
          </BlurFade>
        </TabsContent>

        <TabsContent value="activity" className="mt-4">
          <BlurFade>
            <section className="relative overflow-hidden rounded-3xl border border-border/70 bg-card/60 p-5 md:p-6">
              <BorderBeam size={180} duration={12} colorFrom="#f59e0b" colorTo="#ffffff" />
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-xl font-medium tracking-tight">Recent activity</h2>
                  <p className="text-sm text-muted-foreground">What happened in your workspace</p>
                </div>
                <Badge variant="outline" className="rounded-full">
                  Demo feed
                </Badge>
              </div>
              <AnimatedList>
                {f.activity.map((a) => (
                  <div
                    key={a.id}
                    className="flex items-start gap-3 rounded-2xl border border-border/60 bg-background/40 px-4 py-3 transition-colors hover:border-white/15 hover:bg-white/5"
                  >
                    <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10 text-white/80">
                      <Wallet className="h-3.5 w-3.5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-medium">{friendlyActivityTitle(a.title)}</p>
                        <span className="text-[11px] text-muted-foreground">Demo</span>
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {friendlyActivityDetail(a.detail)}
                      </p>
                    </div>
                  </div>
                ))}
              </AnimatedList>
              <div className="mt-5">
                <Link href="/notifications" className="text-sm text-white/60 hover:text-white">
                  View all updates →
                </Link>
              </div>
            </section>
          </BlurFade>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function friendlyActivityTitle(title: string) {
  if (title.toLowerCase().includes("offline")) return "Agents are resting";
  if (title.toLowerCase().includes("fixture")) return "Demo snapshot loaded";
  if (title.toLowerCase().includes("trading")) return "Live trading stays off";
  return title;
}

function friendlyActivityDetail(detail: string) {
  if (detail.toLowerCase().includes("heartbeat")) {
    return "No agent heartbeat yet — browse markets or try paper trading.";
  }
  if (detail.toLowerCase().includes("sample")) {
    return "You’re viewing labeled demo numbers so nothing looks like live money.";
  }
  if (detail.toLowerCase().includes("disabled")) {
    return "Order buttons stay locked for safety until you unlock them.";
  }
  return detail;
}
