import { proxyPublicPaperGet } from "@/lib/security/public-paper-proxy";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await context.params;
  return proxyPublicPaperGet(
    request,
    `/api/v1/paper/sessions/${sessionId}/fills`,
  );
}
