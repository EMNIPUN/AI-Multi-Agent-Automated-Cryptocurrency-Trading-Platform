"use client";

import { PageFrame } from "@/components/command-center";

import { NewsDashboard } from "./NewsDashboard";

export default function NewsPage() {
  return (
    <PageFrame
      title="News Intelligence"
      description="Market headlines and alerts for research — never trading authority."
      modes={["readonly", "live"]}
    >
      <NewsDashboard />
    </PageFrame>
  );
}
