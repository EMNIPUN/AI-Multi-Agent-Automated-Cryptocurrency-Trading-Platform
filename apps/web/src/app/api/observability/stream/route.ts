import { NextResponse } from "next/server";

/**
 * Same-origin SSE proxy placeholder.
 * Live private streams remain disabled until ownership + flags are verified.
 * Clients must not put JWTs in EventSource query strings.
 */
export async function GET() {
  return NextResponse.json(
    {
      detail: "observability_live_stream_disabled",
      message:
        "Live SSE is disabled for Phase 3A. Use snapshot fixtures. Authenticate via Authorization header through this same-origin proxy when live is enabled.",
    },
    { status: 403 },
  );
}
