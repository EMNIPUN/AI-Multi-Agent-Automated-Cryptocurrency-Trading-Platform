import { proxyPublicNewsGet } from "@/lib/security/public-news-proxy";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ symbol: string }> };

export async function GET(request: Request, ctx: Ctx) {
  const { symbol } = await ctx.params;
  return proxyPublicNewsGet(
    request,
    `/api/v1/news/context/${encodeURIComponent(symbol)}`,
  );
}
