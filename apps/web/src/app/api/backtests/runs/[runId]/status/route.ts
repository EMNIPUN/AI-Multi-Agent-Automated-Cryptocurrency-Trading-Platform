import { proxyPublicBacktestGet } from "@/lib/security/public-backtest-proxy";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ runId: string }> };

export async function GET(request: Request, ctx: Ctx) {
  const { runId } = await ctx.params;
  return proxyPublicBacktestGet(
    request,
    `/api/v1/backtests/runs/${encodeURIComponent(runId)}/status`,
  );
}
