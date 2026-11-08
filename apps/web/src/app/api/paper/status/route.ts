import { proxyPublicPaperGet } from "@/lib/security/public-paper-proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return proxyPublicPaperGet(request, "/api/v1/paper/status");
}
