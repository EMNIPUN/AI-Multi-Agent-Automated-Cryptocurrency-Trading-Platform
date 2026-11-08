import type { Metadata } from "next";

import { LandingPage } from "@/components/landing/LandingPage";

export const metadata: Metadata = {
  title: "CryptoNova — Intelligent Trading. Disciplined Execution.",
  description:
    "Multi-agent cryptocurrency trading platform. Paper-first, SAMPLE-safe, with public markets and gated private reads.",
};

export default function HomePage() {
  return <LandingPage />;
}
