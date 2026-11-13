"use client";

import { WalletBalancePanel } from "@/components/WalletBalancePanel";
import { SectionPanel } from "@/components/command-center";
import { OverviewTemplate } from "@/components/design-system/templates";
import { BlurFade } from "@/components/magicui/blur-fade";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

export default function PortfolioPage() {
  return (
    <OverviewTemplate
      title="Portfolio"
      description="Live Bybit UNIFIED wallet via the server-side read adapter. Allocation shares are computed only from returned coin equity — nothing is invented."
      modes={["readonly"]}
    >
      <DataModeBanner
        mode="demo"
        notes={[
          "Wallet panel uses the live API only when FastAPI wallet reads are enabled.",
          "Coin share % is derived from total equity returned by Bybit.",
          "No fabricated allocation charts beyond API-backed balances.",
        ]}
      />

      <BlurFade>
        <div className="hidden h-[min(78vh,52rem)] overflow-hidden rounded-3xl border border-border bg-muted/40 lg:block">
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
                    <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-brand">
                      How to read this
                    </p>
                    <h2 className="mt-1 text-lg font-medium tracking-tight text-foreground">
                      Portfolio safety notes
                    </h2>
                  </div>
                  <Separator className="bg-muted/40" />
                  <ul className="space-y-2 text-sm text-foreground">
                    <li>
                      <span className="text-foreground">Overview</span> shows top holdings and
                      snapshot facts before you dig into the table.
                    </li>
                    <li>
                      <span className="text-foreground">Filters</span> only hide rows; they never
                      invent balances.
                    </li>
                    <li>
                      <span className="text-foreground">Open P&L</span> is perpetual unrealised P&L
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
        <SectionPanel title="Holdings" description="Mobile wallet snapshot">
          <WalletBalancePanel />
        </SectionPanel>
      </div>
    </OverviewTemplate>
  );
}
