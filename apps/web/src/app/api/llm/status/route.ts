import { proxyPublicLlmGet } from "@/lib/security/public-llm-proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return proxyPublicLlmGet(request, "/api/v1/llm/status");
}
