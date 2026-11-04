import { NextResponse } from "next/server";

/**
 * Same-origin proxy for Bybit UNIFIED wallet.
 * Keys stay on the FastAPI server — never sent to the browser.
 */
export async function GET() {
  const base =
    process.env.API_INTERNAL_BASE_URL?.replace(/\/$/, "") ||
    "http://127.0.0.1:8000";
  try {
    const res = await fetch(`${base}/api/v1/exchange/wallet`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const body = await res.json().catch(() => ({ detail: "invalid_json" }));
    return NextResponse.json(body, { status: res.status });
  } catch {
    return NextResponse.json(
      {
        detail: "api_unreachable",
        message:
          "FastAPI not reachable at API_INTERNAL_BASE_URL / 127.0.0.1:8000",
      },
      { status: 503 },
    );
  }
}
