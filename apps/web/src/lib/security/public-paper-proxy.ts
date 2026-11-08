/**
 * Same-origin proxy for Prompt 65B paper read-only FastAPI routes.
 * GET allowlist only — never wallet/orders/mutations.
 */

import { NextResponse } from "next/server";

import { apiInternalBase } from "@/lib/security/authenticated-proxy";

const ALLOWED_EXACT = [
  "/api/v1/paper/status",
  "/api/v1/paper/sessions",
] as const;

export function isAllowedPublicPaperPath(path: string): boolean {
  const bare = path.split("?")[0];
  if (ALLOWED_EXACT.some((p) => bare === p)) return true;
  if (/^\/api\/v1\/paper\/sessions\/[A-Za-z0-9_]{1,64}$/.test(bare)) return true;
  if (
    /^\/api\/v1\/paper\/sessions\/[A-Za-z0-9_]{1,64}\/(account|positions|orders|fills|events)$/.test(
      bare,
    )
  ) {
    return true;
  }
  if (
    /^\/api\/v1\/paper\/sessions\/[A-Za-z0-9_]{1,64}\/analytics(\/(trades|equity|symbols))?$/.test(
      bare,
    )
  ) {
    return true;
  }
  if (/^\/api\/v1\/paper\/orders\/by-signal\/[A-Za-z0-9_.:\-]{1,128}$/.test(bare)) {
    return true;
  }
  return false;
}

export async function proxyPublicPaperGet(
  request: Request,
  upstreamPath: string,
): Promise<Response> {
  const bare = upstreamPath.split("?")[0];
  if (!isAllowedPublicPaperPath(bare)) {
    return NextResponse.json(
      { detail: "path_not_allowed", message: "Not a public paper read endpoint" },
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
        message: "FastAPI not reachable for paper read API",
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
