import { proxyPublicNewsGet } from "@/lib/security/public-news-proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return proxyPublicNewsGet(request, "/api/v1/news/status");
}
