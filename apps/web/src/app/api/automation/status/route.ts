import { NextResponse } from "next/server";

import { apiInternalBase } from "@/lib/security/authenticated-proxy";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await fetch(`${apiInternalBase()}/api/v1/automation/status`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      redirect: "error",
    });
    const payload = await res.json().catch(() => ({ detail: "invalid_json" }));
    return NextResponse.json(payload, {
      status: res.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { detail: "api_unreachable", message: "FastAPI not reachable for automation status" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
