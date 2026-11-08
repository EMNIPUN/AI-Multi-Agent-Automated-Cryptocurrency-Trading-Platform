import { proxyPublicNewsGet } from "@/lib/security/public-news-proxy";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ eventId: string }> };

export async function GET(request: Request, ctx: Ctx) {
  const { eventId } = await ctx.params;
  return proxyPublicNewsGet(
    request,
    `/api/v1/news/events/${encodeURIComponent(eventId)}`,
  );
}
