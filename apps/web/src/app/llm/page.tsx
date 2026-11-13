"use client";

import { AiWorkspaceTemplate } from "@/components/design-system/templates";

import { LlmDashboard } from "./LlmDashboard";

export default function LlmPage() {
  return (
    <AiWorkspaceTemplate
      title="LLM Intelligence"
      description="Advisory LLM evaluations and reports. Never directs live execution."
      modes={["readonly"]}
    >
      <LlmDashboard />
    </AiWorkspaceTemplate>
  );
}
