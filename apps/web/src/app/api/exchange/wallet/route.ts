import { proxyJsonToFastApi } from "@/lib/security/authenticated-proxy";

/**
 * Same-origin wallet proxy.
 * Prefer Authorization: Bearer <user JWT> → FastAPI owner-bound path.
 * Optional OPERATOR_LOCAL_BROWSER_PROXY_ENABLED break-glass is operator-local only
 * and never used when a user JWT is present.
 */
export async function GET(request: Request) {
  return proxyJsonToFastApi(request, "/api/v1/exchange/wallet", {
    allowOperatorBreakGlass: true,
  });
}
