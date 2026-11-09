"use client";

import { PageFrame } from "@/components/command-center";
import { AgentStudio } from "@/features/agent-studio/components/AgentStudio";

export default function AgentsLivePage() {
  return (
    <PageFrame
      title="Live AI Analysis"
      description="Live market-data analysis — not live-money trading. Signals are research only; execution stays paper/locked."
      modes={["readonly", "live", "paper"]}
    >
      <AgentStudio />
    </PageFrame>
  );
}
