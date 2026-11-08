"use client";

import { Suspense } from "react";

import { LogoLoader } from "@/components/brand/LogoLoader";

import { BacktestingDashboard } from "./BacktestingDashboard";

export default function BacktestingPage() {
  return (
    <Suspense fallback={<LogoLoader fullScreen label="Loading backtesting…" />}>
      <BacktestingDashboard />
    </Suspense>
  );
}
