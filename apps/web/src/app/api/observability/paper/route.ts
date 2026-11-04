import { NextResponse } from "next/server";

import { localPaperFixture } from "@/lib/fixtures/agentSnapshot";

export async function GET() {
  const base = process.env.API_INTERNAL_BASE_URL?.replace(/\/$/, "");
  if (base) {
    try {
      const res = await fetch(`${base}/api/v1/observability/paper/snapshot`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (res.ok) {
        return NextResponse.json(await res.json());
      }
    } catch {
      // local fixture
    }
  }
  return NextResponse.json(localPaperFixture());
}
