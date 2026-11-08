import { proxyPublicBacktestGet } from "@/lib/security/public-backtest-proxy";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ jobId: string }> };

export async function GET(request: Request, ctx: Ctx) {
  const { jobId } = await ctx.params;
  return proxyPublicBacktestGet(
    request,
    `/api/v1/backtests/jobs/${encodeURIComponent(jobId)}`,
  );
}
