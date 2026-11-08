import { proxyPublicNewsGet, proxyPublicNewsPut } from "@/lib/security/public-news-proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return proxyPublicNewsGet(request, "/api/v1/news/alert-settings");
}

export async function PUT(request: Request) {
  return proxyPublicNewsPut(request, "/api/v1/news/alert-settings");
}
