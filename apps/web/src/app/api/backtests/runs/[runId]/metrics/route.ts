import { proxyPublicBacktestGet } from "@/lib/security/public-backtest-proxy";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ runId: string }> },
) {
  const { runId } = await context.params;
  return proxyPublicBacktestGet(request, `/api/v1/backtests/runs/${runId}/metrics`);
}
