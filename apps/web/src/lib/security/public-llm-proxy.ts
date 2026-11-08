/**
 * Same-origin read proxy for Prompt 69D LLM status and audit history.
 * POST /evaluate is intentionally not proxied, so the browser cannot spend the budget.
 */

import { NextResponse } from "next/server";

import { apiInternalBase } from "@/lib/security/authenticated-proxy";

const ALLOWED_GET = [
  "/api/v1/llm/status",
  "/api/v1/llm/evaluations",
  "/api/v1/llm/comparisons",
  "/api/v1/llm/report",
] as const;

export function isAllowedPublicLlmGetPath(path: string): boolean {
  const bare = path.split("?")[0];
  if (ALLOWED_GET.some((item) => bare === item)) return true;
  return /^\/api\/v1\/llm\/evaluations\/lle_[a-z0-9]+$/.test(bare);
}

export function isLlmEvaluatePath(path: string): boolean {
  return path.split("?")[0] === "/api/v1/llm/evaluate";
}

export async function proxyPublicLlmGet(request: Request, upstreamPath: string): Promise<Response> {
  const bare = upstreamPath.split("?")[0];
  if (!isAllowedPublicLlmGetPath(bare) || isLlmEvaluatePath(bare)) {
    return NextResponse.json(
      { detail: "path_not_allowed", message: "Not a public LLM read endpoint" },
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
      { detail: "api_unreachable", message: "FastAPI not reachable for LLM status" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
