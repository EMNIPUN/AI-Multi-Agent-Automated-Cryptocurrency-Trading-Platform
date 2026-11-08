import { proxyJsonToFastApi } from "@/lib/security/authenticated-proxy";

type RouteContext = { params: Promise<{ id: string }> };

export async function POST(request: Request, context: RouteContext) {
  const { id } = await context.params;
  return proxyJsonToFastApi(
    request,
    `/api/v1/exchange/bindings/${encodeURIComponent(id)}/revoke`,
    {
      allowOperatorBreakGlass: false,
      method: "POST",
    },
  );
}
