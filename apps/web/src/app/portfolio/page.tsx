"use client";

import { WalletBalancePanel } from "@/components/WalletBalancePanel";
import { BlurFade } from "@/components/magicui/blur-fade";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export default function PortfolioPage() {
  return (
    <div className="space-y-4 pb-6">
      <PageHeader
        title="Portfolio"
        description="Live Bybit UNIFIED wallet via the server-side read adapter. Allocation shares are computed only from returned coin equity — nothing is invented."
      />
      <DataModeBanner
        mode="demo"
        notes={[
          "Wallet panel uses the live API only when FastAPI wallet reads are enabled.",
          "Coin share % is derived from total equity returned by Bybit.",
          "No fabricated allocation charts beyond API-backed balances.",
        ]}
      />

      <BlurFade>
        <div className="hidden h-[min(78vh,52rem)] overflow-hidden rounded-3xl border border-white/10 bg-black/20 lg:block">
          <ResizablePanelGroup direction="vertical" className="h-full">
            <ResizablePanel defaultSize={74} minSize={48}>
              <ScrollArea className="h-full">
                <div className="p-3 md:p-4">
                  <WalletBalancePanel />
                </div>
              </ScrollArea>
            </ResizablePanel>
            <ResizableHandle withHandle />
            <ResizablePanel defaultSize={26} minSize={16}>
              <ScrollArea className="h-full">
                <div className="flex flex-col gap-3 p-4 md:p-5">
                  <div>
                    <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-amber-200/80">
                      How to read this
                    </p>
                    <h2 className="mt-1 text-lg font-medium tracking-tight text-white">
                      Portfolio safety notes
                    </h2>
                  </div>
                  <Separator className="bg-white/10" />
                  <ul className="space-y-2 text-sm text-white/60">
                    <li>
                      <span className="text-white/90">Overview</span> shows top holdings and
                      snapshot facts before you dig into the table.
                    </li>
                    <li>
                      <span className="text-white/90">Filters</span> — All, Majors, With P&L,
                      Dust (&lt;1% share) — only hide rows; they never invent balances.
                    </li>
                    <li>
                      <span className="text-white/90">Open P&L</span> is perpetual unrealised P&L
                      only — not closed trades.
                    </li>
                  </ul>
                </div>
              </ScrollArea>
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      </BlurFade>

      <div className="lg:hidden">
        <WalletBalancePanel />
      </div>
    </div>
  );
}
