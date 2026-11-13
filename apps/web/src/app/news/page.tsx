"use client";

import { ResearchTemplate } from "@/components/design-system/templates";

import { NewsDashboard } from "./NewsDashboard";

export default function NewsPage() {
  return (
    <ResearchTemplate
      title="News Intelligence"
      description="Market headlines and alerts for research — never trading authority."
      modes={["readonly"]}
    >
      <NewsDashboard />
    </ResearchTemplate>
  );
}
