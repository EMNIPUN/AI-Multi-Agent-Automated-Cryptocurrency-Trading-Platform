import { proxyPublicNewsPost } from "@/lib/security/public-news-proxy";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  context: { params: Promise<{ alertId: string }> },
) {
  const { alertId } = await context.params;
  return proxyPublicNewsPost(request, `/api/v1/news/alerts/${alertId}/acknowledge`);
}
