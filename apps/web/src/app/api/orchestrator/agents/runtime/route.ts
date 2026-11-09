import { proxyOrchestrator } from "@/lib/orchestrator/operator-proxy";

export async function GET(request: Request) {
  return proxyOrchestrator(request, "agents/runtime");
}
