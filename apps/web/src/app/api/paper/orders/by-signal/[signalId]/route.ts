import { proxyPublicPaperGet } from "@/lib/security/public-paper-proxy";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ signalId: string }> },
) {
  const { signalId } = await context.params;
  return proxyPublicPaperGet(
    request,
    `/api/v1/paper/orders/by-signal/${signalId}`,
  );
}
