import { proxyOrchestrator } from "@/lib/orchestrator/operator-proxy";

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  return proxyOrchestrator(request, `conversations/${encodeURIComponent(id)}`);
}
