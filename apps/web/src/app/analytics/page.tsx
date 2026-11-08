"use client";

import { Suspense } from "react";

import { LogoLoader } from "@/components/brand/LogoLoader";

import { AnalyticsDashboard } from "./AnalyticsDashboard";

export default function AnalyticsPage() {
  return (
    <Suspense fallback={<LogoLoader fullScreen label="Loading analytics…" />}>
      <AnalyticsDashboard />
    </Suspense>
  );
}
