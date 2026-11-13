"use client";

import { AiWorkspaceTemplate } from "@/components/design-system/templates";
import { AgentStudio } from "@/features/agent-studio/components/AgentStudio";

export default function AgentsLivePage() {
  return (
    <AiWorkspaceTemplate
      title="Live AI Analysis"
      description="Live market-data analysis — not live-money trading. Signals are research only; execution stays paper/locked."
      modes={["readonly", "paper"]}
    >
      <AgentStudio />
    </AiWorkspaceTemplate>
  );
}
