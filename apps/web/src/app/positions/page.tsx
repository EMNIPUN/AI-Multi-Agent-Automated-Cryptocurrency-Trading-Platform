"use client";

import { PositionsOrdersPanel } from "@/components/PositionsOrdersPanel";
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

export default function PositionsPage() {
  return (
    <div className="space-y-4 pb-6">
      <PageHeader
        title="Positions & orders"
        description="Read-only positions, open orders, and fills. Cancel and place controls are not part of this UI."
      />
      <DataModeBanner
        mode="unavailable"
        notes={[
          "Live exchange position APIs stay gated.",
          "Paper journal rows appear only when PAPER_READ_API is enabled.",
          "ACCEPTED does not mean FILLED.",
        ]}
      />

      <BlurFade>
        <div className="hidden h-[min(78vh,52rem)] overflow-hidden rounded-3xl border border-white/10 bg-black/20 lg:block">
          <ResizablePanelGroup direction="vertical" className="h-full">
            <ResizablePanel defaultSize={74} minSize={48}>
              <ScrollArea className="h-full">
                <div className="p-3 md:p-4">
                  <PositionsOrdersPanel />
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
                      Positions safety notes
                    </h2>
                  </div>
                  <Separator className="bg-white/10" />
                  <ul className="space-y-2 text-sm text-white/60">
                    <li>
                      <span className="text-white/90">Overview</span> summarizes open exposure and
                      adapter facts before the tables.
                    </li>
                    <li>
                      <span className="text-white/90">Filters</span> only hide rows — they never
                      invent positions or fills.
                    </li>
                    <li>
                      <span className="text-white/90">ACCEPTED ≠ FILLED</span> — order status is
                      shown exactly as the journal reports it.
                    </li>
                  </ul>
                </div>
              </ScrollArea>
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      </BlurFade>

      <div className="lg:hidden">
        <PositionsOrdersPanel />
      </div>
    </div>
  );
}
