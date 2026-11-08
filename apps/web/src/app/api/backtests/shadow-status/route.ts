import { proxyPublicBacktestGet } from "@/lib/security/public-backtest-proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return proxyPublicBacktestGet(request, "/api/v1/backtests/shadow-status");
}
