"use client";

import { PageFrame } from "@/components/command-center";

import { LlmDashboard } from "./LlmDashboard";

export default function LlmPage() {
  return (
    <PageFrame
      title="LLM Intelligence"
      description="Advisory LLM evaluations and reports. Never directs live execution."
      modes={["readonly", "live"]}
    >
      <LlmDashboard />
    </PageFrame>
  );
}
