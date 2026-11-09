"use client";

import Link from "next/link";
import { Activity, History } from "lucide-react";

import { PageFrame, SectionPanel } from "@/components/command-center";
import { SignalsPanel } from "@/features/agent-studio/components/SignalsPanel";
import { Button } from "@/components/ui/button";

export default function StrategyResearchPage() {
  return (
    <PageFrame
      title="Strategy Research"
      description="Closed-candle signal research from the multi-agent pipeline. Signals are not orders — live trading stays locked."
      modes={["readonly", "live", "paper"]}
      actions={
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm" className="rounded-full">
            <Link href="/agents/live">
              <Activity className="mr-1.5 h-3.5 w-3.5" />
              Live AI Analysis
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm" className="rounded-full">
            <Link href="/backtesting">
              <History className="mr-1.5 h-3.5 w-3.5" />
              Backtesting
            </Link>
          </Button>
        </div>
      }
    >
      <SectionPanel
        title="Signal engine"
        description="Reuses the existing Phase 4B/4C evaluate + history adapters. No new trading permissions."
        beam
      >
        <SignalsPanel symbol="BTCUSDT" category="linear" interval="15" />
      </SectionPanel>
    </PageFrame>
  );
}
