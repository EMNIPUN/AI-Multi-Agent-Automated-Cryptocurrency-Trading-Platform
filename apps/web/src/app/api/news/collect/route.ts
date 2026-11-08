import { proxyPublicNewsPost } from "@/lib/security/public-news-proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  return proxyPublicNewsPost(request, "/api/v1/news/collect");
}
