/**
 * Same-origin proxy for *public* Bybit market data via FastAPI.
 * No JWT required. Path allowlist only — never proxies private/exchange routes.
 */

import { NextResponse } from "next/server";

import { apiInternalBase } from "@/lib/security/authenticated-proxy";

const ALLOWED_PREFIXES = [
  "/api/v1/market/status",
  "/api/v1/market/tickers",
  "/api/v1/market/klines",
  "/api/v1/market/orderbook",
  "/api/v1/market/trades",
  "/api/v1/market/meta",
] as const;

export function isAllowedPublicMarketPath(path: string): boolean {
  const bare = path.split("?")[0];
  return ALLOWED_PREFIXES.some((p) => bare === p);
}

export async function proxyPublicMarketGet(
  request: Request,
  upstreamPath: string,
): Promise<Response> {
  if (!isAllowedPublicMarketPath(upstreamPath.split("?")[0])) {
    return NextResponse.json(
      { detail: "path_not_allowed", message: "Not a public market endpoint" },
      { status: 403 },
    );
  }
  const url = new URL(request.url);
  const qs = url.searchParams.toString();
  const target = `${apiInternalBase()}${upstreamPath}${qs ? `?${qs}` : ""}`;
  try {
    const res = await fetch(target, {
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
      {
        detail: "api_unreachable",
        message: "FastAPI not reachable for public market data",
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
