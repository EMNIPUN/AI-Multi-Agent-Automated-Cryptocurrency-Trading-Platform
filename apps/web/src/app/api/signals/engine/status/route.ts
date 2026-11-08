import { proxyPublicSignalsGet } from "@/lib/security/public-signals-proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return proxyPublicSignalsGet(request, "/api/v1/signals/engine/status");
}
