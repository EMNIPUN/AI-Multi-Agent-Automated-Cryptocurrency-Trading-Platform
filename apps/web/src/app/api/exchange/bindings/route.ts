import { proxyJsonToFastApi } from "@/lib/security/authenticated-proxy";

export async function GET(request: Request) {
  return proxyJsonToFastApi(request, "/api/v1/exchange/bindings", {
    allowOperatorBreakGlass: false,
    method: "GET",
  });
}

export async function POST(request: Request) {
  return proxyJsonToFastApi(request, "/api/v1/exchange/bindings", {
    allowOperatorBreakGlass: false,
    method: "POST",
    forwardBody: true,
  });
}
