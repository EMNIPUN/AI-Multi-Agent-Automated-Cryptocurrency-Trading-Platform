import { proxyPublicNewsGet } from "@/lib/security/public-news-proxy";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ alertId: string }> },
) {
  const { alertId } = await context.params;
  return proxyPublicNewsGet(request, `/api/v1/news/alerts/${alertId}`);
}
