import { afterEach, describe, expect, it, vi } from "vitest";

import { operatorProxyError, proxyOrchestrator } from "./operator-proxy";

const env = { OPERATOR_LOCAL_BROWSER_PROXY_ENABLED: "true" };
const local = "http://localhost:3000/api/orchestrator/command";
const request = (headers: Record<string, string> = {}, url = local, method = "POST") => new Request(url, { method, headers: { origin: "http://localhost:3000", ...headers } });

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe("operator proxy authorization boundary", () => {
  it("requires explicit local operator opt-in", () => {
    expect(operatorProxyError(request(), {})).toBe("operator_local_proxy_disabled");
    expect(operatorProxyError(request(), env)).toBeNull();
    expect(operatorProxyError(request(), { ...env, APP_ENV: "production" })).toBe("operator_controls_disabled_in_production");
  });

  it("rejects remote hosts, origin spoofing and remote forwarded addresses", () => {
    expect(operatorProxyError(request({}, "https://console.example/api/orchestrator/command"), env)).toBe("operator_local_only");
    expect(operatorProxyError(request({ origin: "https://attacker.example" }), env)).toBe("csrf_origin_mismatch");
    expect(operatorProxyError(request({ "sec-fetch-site": "cross-site" }), env)).toBe("csrf_origin_mismatch");
    expect(operatorProxyError(request({ "x-forwarded-for": "203.0.113.20" }), env)).toBe("operator_forwarded_request_rejected");
    expect(operatorProxyError(request({ "x-forwarded-for": "127.0.0.1, 203.0.113.20" }), env)).toBe("operator_forwarded_request_rejected");
    expect(operatorProxyError(request({ forwarded: "for=127.0.0.1" }), env)).toBe("operator_forwarded_request_rejected");
  });

  it("accepts Next.js loopback socket headers and requires origin on mutations", () => {
    expect(operatorProxyError(request({ "x-forwarded-for": "::ffff:127.0.0.1", "sec-fetch-site": "same-origin" }), env)).toBeNull();
    expect(operatorProxyError(new Request(local, { method: "POST" }), env)).toBe("csrf_origin_required");
    expect(operatorProxyError(new Request(local), env)).toBeNull();
  });

  it("will not forward privileged requests to a remote configured API", () => {
    expect(operatorProxyError(request(), { ...env, API_INTERNAL_BASE_URL: "https://api.example" })).toBe("operator_api_must_be_local");
    expect(operatorProxyError(request(), { ...env, API_INTERNAL_BASE_URL: "http://user:pass@localhost:8000" })).toBe("operator_api_must_be_local");
    expect(operatorProxyError(request(), { ...env, API_INTERNAL_BASE_URL: "invalid" })).toBe("operator_api_must_be_local");
  });

  it.each(["status", "report", "chat", "command"] as const)("does not contact the API when %s is denied", async (route) => {
    vi.stubEnv("OPERATOR_LOCAL_BROWSER_PROXY_ENABLED", "false");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const response = await proxyOrchestrator(request(), route);
    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards a bounded command without browser credentials or forwarding headers", async () => {
    vi.stubEnv("OPERATOR_LOCAL_BROWSER_PROXY_ENABLED", "true");
    vi.stubEnv("APP_ENV", "development");
    vi.stubEnv("API_INTERNAL_BASE_URL", "http://127.0.0.1:8000");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ state: "PAUSED", live_orders: false })));
    vi.stubGlobal("fetch", fetchMock);
    const response = await proxyOrchestrator(new Request(local, { method: "POST", headers: { origin: "http://localhost:3000", cookie: "private=session", "x-forwarded-for": "127.0.0.1" }, body: JSON.stringify({ command: "pause" }) }), "command");
    expect(response.status).toBe(200);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/api/v1/orchestrator/command");
    expect(options.body).toBe('{"command":"pause"}');
    expect(options.redirect).toBe("error");
    expect(options.headers).not.toHaveProperty("cookie");
    expect(options.headers).not.toHaveProperty("x-forwarded-for");
  });
});
