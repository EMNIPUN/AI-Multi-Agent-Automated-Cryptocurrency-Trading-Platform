import { proxyPublicLlmGet } from "@/lib/security/public-llm-proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: Promise<{ evaluationId: string }> }) {
  const { evaluationId } = await context.params;
  return proxyPublicLlmGet(request, `/api/v1/llm/evaluations/${evaluationId}`);
}
