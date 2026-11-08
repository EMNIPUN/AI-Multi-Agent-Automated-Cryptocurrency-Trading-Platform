/**
 * Browser → Next.js → FastAPI authenticated proxy helpers.
 * Never treat operator-local break-glass as user authorization.
 */

import { NextResponse } from "next/server";

import { operatorLocalBrowserProxyEnabled } from "@/lib/security/operator-proxy-gate";

export function apiInternalBase(): string {
  return (
    process.env.API_INTERNAL_BASE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000"
  );
}

export function bearerFromRequest(request: Request): string | null {
  const auth = request.headers.get("authorization");
  if (!auth) return null;
  const [scheme, token] = auth.split(/\s+/, 2);
  if (!scheme || scheme.toLowerCase() !== "bearer" || !token?.trim()) return null;
  return token.trim();
}

export async function proxyJsonToFastApi(
  request: Request,
  path: string,
  options: {
    allowOperatorBreakGlass: boolean;
    method?: string;
    forwardBody?: boolean;
  },
): Promise<Response> {
  const allowOperatorBreakGlass = options.allowOperatorBreakGlass;
  const method = (options.method || request.method || "GET").toUpperCase();
  const token = bearerFromRequest(request);
  const breakGlass = operatorLocalBrowserProxyEnabled();

  // Authenticated path: forward JWT only — never mix with break-glass.
  // Do not forward X-Forwarded-For / X-Real-IP / cookies (operator-local gate rejects them).
  if (token) {
    try {
      const headers: Record<string, string> = {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      };
      let body: string | undefined;
      if (options.forwardBody && method !== "GET" && method !== "HEAD") {
        body = await request.text();
        if (body) headers["Content-Type"] = "application/json";
      }
      const res = await fetch(`${apiInternalBase()}${path}`, {
        method,
        headers,
        body,
        cache: "no-store",
        redirect: "error",
      });
      const payload = await res.json().catch(() => ({ detail: "invalid_json" }));
      return NextResponse.json(payload, {
        status: res.status,
        headers: {
          "Cache-Control": "no-store",
        },
      });
    } catch {
      return NextResponse.json(
        { detail: "api_unreachable", message: "FastAPI not reachable" },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }
  }

  // Unauthenticated browser: fail closed unless explicit single-operator break-glass.
  if (!allowOperatorBreakGlass || !breakGlass) {
    return NextResponse.json(
      {
        detail: "authentication_required",
        message:
          "Provide Authorization: Bearer <Supabase access token>. Operator-local break-glass is not a multi-user auth shortcut.",
      },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }

  try {
    const res = await fetch(`${apiInternalBase()}${path}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const body = await res.json().catch(() => ({ detail: "invalid_json" }));
    return NextResponse.json(body, {
      status: res.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      {
        detail: "api_unreachable",
        message: "FastAPI not reachable at API_INTERNAL_BASE_URL / 127.0.0.1:8000",
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
