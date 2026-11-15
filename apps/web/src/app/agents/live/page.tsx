"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { AiWorkspaceTemplate } from "@/components/design-system/templates";
import { Button } from "@/components/ui/button";
import { AgentStudio } from "@/features/agent-studio/components/AgentStudio";
import { LiveAnalysisPanel } from "@/features/agents/components/LiveAnalysisPanel";
import { cn } from "@/lib/utils";

export default function AgentsLivePage() {
  const [studioOpen, setStudioOpen] = useState(false);
  return (
    <AiWorkspaceTemplate
      title="Live Market Analysis"
      description="Live means current public market data, not live-money trading. Signals here are research output; execution stays paper or locked."
      modes={["readonly", "paper"]}
    >
      <LiveAnalysisPanel />
      <section className="cn-panel p-4 md:p-5">
        <button
          type="button"
          className="flex w-full items-center justify-between gap-3 text-left"
          onClick={() => setStudioOpen((v) => !v)}
          aria-expanded={studioOpen}
          aria-controls="worker-telemetry-studio"
        >
          <div>
            <h2 className="text-base font-medium tracking-tight text-foreground">Worker telemetry studio</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Observability ledger from the legacy agent runner: workflow stages, event feed, replay. Shows a waiting state when no worker telemetry exists.
            </p>
          </div>
          <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", studioOpen && "rotate-180")} aria-hidden />
        </button>
        {studioOpen ? (
          <div id="worker-telemetry-studio" className="mt-4">
            <AgentStudio />
          </div>
        ) : (
          <Button variant="outline" size="sm" className="mt-3 rounded-full" onClick={() => setStudioOpen(true)}>
            Open studio
          </Button>
        )}
      </section>
    </AiWorkspaceTemplate>
  );
}
