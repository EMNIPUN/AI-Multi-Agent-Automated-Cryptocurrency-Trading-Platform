/**
 * Same-origin proxy for Phase 4B/4C signals-only FastAPI routes.
 * Allowlisted paths only — never wallet/orders/bindings.
 */

import { NextResponse } from "next/server";

import { apiInternalBase } from "@/lib/security/authenticated-proxy";

const ALLOWED_GET = [
  "/api/v1/signals/status",
  "/api/v1/signals/evaluate",
  "/api/v1/signals/history",
  "/api/v1/signals/analytics",
  "/api/v1/signals/engine/status",
  "/api/v1/signals/sync/status",
] as const;

const ALLOWED_POST = [
  "/api/v1/signals/evaluate",
  "/api/v1/signals/engine/start",
  "/api/v1/signals/engine/stop",
] as const;

export function isAllowedPublicSignalsPath(path: string): boolean {
  const bare = path.split("?")[0];
  if (ALLOWED_GET.some((p) => bare === p)) return true;
  if (ALLOWED_POST.some((p) => bare === p)) return true;
  if (/^\/api\/v1\/signals\/history\/dec_[a-f0-9]+$/i.test(bare)) return true;
  return false;
}

export function isAllowedPublicSignalsPostPath(path: string): boolean {
  const bare = path.split("?")[0];
  return ALLOWED_POST.some((p) => bare === p);
}

async function proxySignals(
  request: Request,
  upstreamPath: string,
  method: "GET" | "POST",
): Promise<Response> {
  const bare = upstreamPath.split("?")[0];
  if (method === "GET" && !isAllowedPublicSignalsPath(bare)) {
    return NextResponse.json(
      { detail: "path_not_allowed", message: "Not a public signals endpoint" },
      { status: 403 },
    );
  }
  if (method === "POST" && !isAllowedPublicSignalsPostPath(bare)) {
    return NextResponse.json(
      { detail: "path_not_allowed", message: "Not an allowed signals POST" },
      { status: 403 },
    );
  }
  const url = new URL(request.url);
  const qs = method === "GET" ? url.searchParams.toString() : "";
  const target = `${apiInternalBase()}${upstreamPath}${qs ? `?${qs}` : ""}`;
  try {
    const init: RequestInit = {
      method,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      cache: "no-store",
      redirect: "error",
    };
    if (method === "POST") {
      const text = await request.text();
      if (text) init.body = text;
    }
    const res = await fetch(target, init);
    const payload = await res.json().catch(() => ({ detail: "invalid_json" }));
    return NextResponse.json(payload, {
      status: res.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      {
        detail: "api_unreachable",
        message: "FastAPI not reachable for signals",
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}

export async function proxyPublicSignalsGet(
  request: Request,
  upstreamPath: string,
): Promise<Response> {
  return proxySignals(request, upstreamPath, "GET");
}

export async function proxyPublicSignalsPost(
  request: Request,
  upstreamPath: string,
): Promise<Response> {
  return proxySignals(request, upstreamPath, "POST");
}
