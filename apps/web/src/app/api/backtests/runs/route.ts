import {
  proxyPublicBacktestGet,
  proxyPublicBacktestPost,
} from "@/lib/security/public-backtest-proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return proxyPublicBacktestGet(request, "/api/v1/backtests/runs");
}

export async function POST(request: Request) {
  return proxyPublicBacktestPost(request, "/api/v1/backtests/runs");
}
