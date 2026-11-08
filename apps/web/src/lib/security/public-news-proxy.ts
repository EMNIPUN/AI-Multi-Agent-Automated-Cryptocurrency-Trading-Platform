/**
 * Same-origin proxy for Prompt 69A news read/collect FastAPI routes.
 */

import { NextResponse } from "next/server";

import { apiInternalBase } from "@/lib/security/authenticated-proxy";

const ALLOWED_GET = [
  "/api/v1/news/status",
  "/api/v1/news/articles",
  "/api/v1/news/events",
  "/api/v1/news/providers/health",
  "/api/v1/news/alerts",
  "/api/v1/news/alerts/unread-count",
  "/api/v1/news/alert-settings",
] as const;

const ALLOWED_POST = ["/api/v1/news/collect"] as const;

export function isAllowedPublicNewsPath(path: string): boolean {
  const bare = path.split("?")[0];
  if (ALLOWED_GET.some((p) => bare === p)) return true;
  if (ALLOWED_POST.some((p) => bare === p)) return true;
  if (/^\/api\/v1\/news\/events\/[A-Za-z0-9_\-]+$/.test(bare)) return true;
  if (/^\/api\/v1\/news\/context\/[A-Z0-9]+$/.test(bare)) return true;
  if (/^\/api\/v1\/news\/alerts\/nal_[a-z0-9]+$/.test(bare)) return true;
  return false;
}

export function isAllowedPublicNewsPostPath(path: string): boolean {
  const bare = path.split("?")[0];
  if (ALLOWED_POST.some((p) => bare === p)) return true;
  return /^\/api\/v1\/news\/alerts\/nal_[a-z0-9]+\/acknowledge$/.test(bare);
}

export function isAllowedPublicNewsPutPath(path: string): boolean {
  return path.split("?")[0] === "/api/v1/news/alert-settings";
}

async function proxyNews(
  request: Request,
  upstreamPath: string,
  method: "GET" | "POST" | "PUT",
): Promise<Response> {
  const bare = upstreamPath.split("?")[0];
  if (method === "GET" && !isAllowedPublicNewsPath(bare)) {
    return NextResponse.json(
      { detail: "path_not_allowed", message: "Not a public news endpoint" },
      { status: 403 },
    );
  }
  if (method === "POST" && !isAllowedPublicNewsPostPath(bare)) {
    return NextResponse.json(
      { detail: "path_not_allowed", message: "Not an allowed news POST" },
      { status: 403 },
    );
  }
  if (method === "PUT" && !isAllowedPublicNewsPutPath(bare)) {
    return NextResponse.json(
      { detail: "path_not_allowed", message: "Not an allowed news PUT" },
      { status: 403 },
    );
  }
  if (method === "POST" || method === "PUT") {
    const origin = request.headers.get("origin");
    if (origin) {
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
    }
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
    if (method === "POST" || method === "PUT") {
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
      { detail: "api_unreachable", message: "FastAPI not reachable for news" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}

export async function proxyPublicNewsGet(request: Request, upstreamPath: string) {
  return proxyNews(request, upstreamPath, "GET");
}

export async function proxyPublicNewsPost(request: Request, upstreamPath: string) {
  return proxyNews(request, upstreamPath, "POST");
}

export async function proxyPublicNewsPut(request: Request, upstreamPath: string) {
  return proxyNews(request, upstreamPath, "PUT");
}
