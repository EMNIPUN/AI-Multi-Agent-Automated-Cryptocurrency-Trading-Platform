"use client";

import Link from "next/link";

import { SectionPanel } from "@/components/command-center";
import { AiWorkspaceTemplate } from "@/components/design-system/templates";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AGENT_REGISTRY } from "@/lib/agents/registry";

export default function AgentsPage() {
  return (
    <AiWorkspaceTemplate
      title="Agent Workspace"
      description="Shared registry aligned with the SignalPipeline spine. Live contributions appear on Autonomous Trading and Live AI Analysis."
      modes={["readonly", "paper"]}
      actions={
        <Button asChild variant="secondary" className="rounded-full">
          <Link href="/autonomy">Open Autonomous Trading</Link>
        </Button>
      }
    >
      <DataModeBanner
        mode="paper"
        notes={[
          "Volume and structure agents are active in STRATEGY_VERSION 6.x.",
          "LLM/news remain advisory and cannot change BUY/SELL.",
          "No agent in this catalog places live exchange orders.",
        ]}
      />
      <SectionPanel title="Registered agents" description="Source: lib/agents/registry.ts ↔ backend REGISTRY">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {AGENT_REGISTRY.map((agent) => (
            <div
              key={agent.agent_id}
              className="rounded-2xl border border-border bg-muted/30 p-4"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-foreground">{agent.label}</p>
                  <p className="mt-1 font-mono text-[10px] text-muted-foreground">{agent.agent_id}</p>
                </div>
                <Badge variant="outline" className="rounded-full">
                  {agent.places_orders ? "Orders" : "Signals"}
                </Badge>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{agent.role}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm" className="rounded-full">
            <Link href="/agents/live">Live AI Analysis</Link>
          </Button>
          <Button asChild variant="ghost" size="sm" className="rounded-full">
            <Link href="/orchestrator">Orchestrator chat</Link>
          </Button>
        </div>
      </SectionPanel>
    </AiWorkspaceTemplate>
  );
}
