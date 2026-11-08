/**
 * Same-origin proxy for Prompt 68B/68C backtest FastAPI routes.
 * GET reads + gated POST run. Never talks to private Bybit trading APIs.
 */

import { NextResponse } from "next/server";

import { apiInternalBase } from "@/lib/security/authenticated-proxy";

const ALLOWED_GET_EXACT = [
    "/api/v1/backtests/status",
    "/api/v1/backtests/runs",
    "/api/v1/backtests/run-capabilities",
    "/api/v1/backtests/shadow-status",
] as const;

const ALLOWED_POST_EXACT = ["/api/v1/backtests/runs"] as const;

const RUN_ID = "bt_[A-Za-z0-9]{8,32}";
const JOB_ID = "btj_[A-Za-z0-9]{8,32}";

export function isAllowedPublicBacktestPath(path: string): boolean {
  const bare = path.split("?")[0];
  if (ALLOWED_GET_EXACT.some((p) => bare === p)) return true;
  if (ALLOWED_POST_EXACT.some((p) => bare === p)) return true;
  if (new RegExp(`^/api/v1/backtests/runs/${RUN_ID}$`).test(bare)) return true;
  if (
    new RegExp(
      `^/api/v1/backtests/runs/${RUN_ID}/(metrics|trades|equity|decisions|orders|status)$`,
    ).test(bare)
  ) {
    return true;
  }
  if (new RegExp(`^/api/v1/backtests/jobs/${JOB_ID}$`).test(bare)) return true;
  if (new RegExp(`^/api/v1/backtests/runs/${JOB_ID}/status$`).test(bare)) return true;
  return false;
}

export function isAllowedPublicBacktestPostPath(path: string): boolean {
  const bare = path.split("?")[0];
  return ALLOWED_POST_EXACT.some((p) => bare === p);
}

function assertSameOrigin(request: Request): Response | null {
  const origin = request.headers.get("origin");
  if (!origin) {
    // Non-browser clients (tests) may omit Origin; require Referer match or allow loopback tooling.
    const referer = request.headers.get("referer");
    if (!referer) return null;
    try {
      const ref = new URL(referer);
      const here = new URL(request.url);
      if (ref.origin !== here.origin) {
        return NextResponse.json(
          { detail: "csrf_origin_mismatch", message: "Cross-origin POST rejected" },
          { status: 403 },
        );
      }
    } catch {
      return NextResponse.json(
        { detail: "csrf_bad_referer", message: "Invalid Referer" },
        { status: 403 },
      );
    }
    return null;
  }
  try {
    const here = new URL(request.url);
    if (origin !== here.origin) {
      return NextResponse.json(
        { detail: "csrf_origin_mismatch", message: "Cross-origin POST rejected" },
        { status: 403 },
      );
    }
  } catch {
    return NextResponse.json(
      { detail: "csrf_bad_origin", message: "Invalid Origin" },
      { status: 403 },
    );
  }
  return null;
}

async function proxyBacktest(
  request: Request,
  upstreamPath: string,
  method: "GET" | "POST",
): Promise<Response> {
  const bare = upstreamPath.split("?")[0];
  if (method === "GET" && !isAllowedPublicBacktestPath(bare)) {
    return NextResponse.json(
      { detail: "path_not_allowed", message: "Not a public backtest endpoint" },
      { status: 403 },
    );
  }
  if (method === "POST") {
    if (!isAllowedPublicBacktestPostPath(bare)) {
      return NextResponse.json(
        { detail: "path_not_allowed", message: "Not an allowed backtest POST" },
        { status: 403 },
      );
    }
    const csrf = assertSameOrigin(request);
    if (csrf) return csrf;
  }
  const url = new URL(request.url);
  const qs = method === "GET" ? url.searchParams.toString() : "";
  const target = `${apiInternalBase()}${upstreamPath}${qs ? `?${qs}` : ""}`;
  try {
    const headers: Record<string, string> = {
      Accept: "application/json",
      "Content-Type": "application/json",
    };
    const idem = request.headers.get("Idempotency-Key");
    if (idem) headers["Idempotency-Key"] = idem;
    const init: RequestInit = {
      method,
      headers,
      cache: "no-store",
      redirect: "error",
    };
    if (method === "POST") {
      const text = await request.text();
      if (text.length > 16_384) {
        return NextResponse.json(
          { detail: "body_too_large", message: "request body exceeds 16KiB" },
          { status: 413 },
        );
      }
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
        message: "FastAPI not reachable for backtest API",
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}

export async function proxyPublicBacktestGet(
  request: Request,
  upstreamPath: string,
): Promise<Response> {
  return proxyBacktest(request, upstreamPath, "GET");
}

export async function proxyPublicBacktestPost(
  request: Request,
  upstreamPath: string,
): Promise<Response> {
  return proxyBacktest(request, upstreamPath, "POST");
}
