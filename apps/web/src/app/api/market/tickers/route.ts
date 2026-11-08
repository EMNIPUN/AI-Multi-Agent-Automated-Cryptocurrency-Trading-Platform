import { proxyPublicMarketGet } from "@/lib/security/public-market-proxy";

export async function GET(request: Request) {
  return proxyPublicMarketGet(request, "/api/v1/market/tickers");
}
