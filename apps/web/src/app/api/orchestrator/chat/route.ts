import { proxyOrchestrator } from "@/lib/orchestrator/operator-proxy";

export const dynamic = "force-dynamic";

export function POST(request: Request) {
  return proxyOrchestrator(request, "chat");
}
