import { NextResponse } from "next/server";

import { apiInternalBase } from "@/lib/security/authenticated-proxy";
import { operatorLocalBrowserProxyEnabled } from "@/lib/security/operator-proxy-gate";

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);

/** Explicit single-operator access. This proxy is not a multi-user authorization boundary. */
export function operatorProxyError(
  request: Request,
  env: Record<string, string | undefined> = process.env,
): string | null {
  if (!operatorLocalBrowserProxyEnabled(env)) return "operator_local_proxy_disabled";
  if (["prod", "production"].includes((env.APP_ENV || "").toLowerCase())) return "operator_controls_disabled_in_production";
  const url = new URL(request.url);
  if (!LOCAL_HOSTS.has(url.hostname)) return "operator_local_only";
  if (request.headers.has("forwarded") || request.headers.has("x-real-ip")) return "operator_forwarded_request_rejected";
  // Next.js adds the socket address here, including for direct local requests.
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor && !["127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(forwardedFor.trim())) return "operator_forwarded_request_rejected";
  const origin = request.headers.get("origin");
  if (origin && origin !== url.origin) return "csrf_origin_mismatch";
  const site = request.headers.get("sec-fetch-site");
  if (site && !["same-origin", "none"].includes(site)) return "csrf_origin_mismatch";
  if (request.method !== "GET" && request.method !== "HEAD" && origin !== url.origin) return "csrf_origin_required";
  try {
    const api = new URL(env.API_INTERNAL_BASE_URL || "http://127.0.0.1:8000");
    if (!LOCAL_HOSTS.has(api.hostname) || !["http:", "https:"].includes(api.protocol) || api.username || api.password) {
      return "operator_api_must_be_local";
    }
  } catch {
    return "operator_api_must_be_local";
  }
  return null;
}

export type OrchestratorProxyRoute =
  | "status"
  | "report"
  | "chat"
  | "command"
  | "autonomy"
  | "decisions"
  | "agents/runtime"
  | "risk";

export async function proxyOrchestrator(request: Request, route: OrchestratorProxyRoute) {
  const error = operatorProxyError(request);
  if (error) return NextResponse.json({ detail: error, live_orders: false }, { status: 403, headers: { "Cache-Control": "no-store" } });
  const isMutation = request.method === "POST";
  try {
    const body = isMutation ? await request.text() : undefined;
    if (body && body.length > 16_384) return NextResponse.json({ detail: "request_too_large" }, { status: 413 });
    const res = await fetch(`${apiInternalBase()}/api/v1/orchestrator/${route}`, {
      method: isMutation ? "POST" : "GET",
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(isMutation && route === "chat" ? 60_000 : 15_000),
      headers: { Accept: "application/json", ...(isMutation ? { "Content-Type": "application/json" } : {}) },
      body,
    });
    const payload = await res.json().catch(() => ({ detail: "invalid_json" }));
    return NextResponse.json(payload, { status: res.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ detail: "api_unreachable", live_orders: false, openai_called: false }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
