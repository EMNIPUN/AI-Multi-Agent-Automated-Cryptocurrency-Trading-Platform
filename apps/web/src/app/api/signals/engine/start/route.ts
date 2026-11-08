import { proxyPublicSignalsPost } from "@/lib/security/public-signals-proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  return proxyPublicSignalsPost(request, "/api/v1/signals/engine/start");
}
