/** Browser → local FastAPI public market stream (never a user-supplied upstream). */
export function marketStreamWsUrl(): string {
  const fromEnv = process.env.NEXT_PUBLIC_MARKET_WS_URL?.trim();
  if (fromEnv) return fromEnv;
  // Default stays 8000 for docs/tests; local Windows may override via NEXT_PUBLIC_MARKET_WS_URL
  // when Hyper-V excludes 8000 (WinError 10013).
  return "ws://127.0.0.1:8000/api/v1/market/stream";
}
