import { describe, expect, it } from "vitest";

import {
  isAllowedPublicSignalsPath,
  isAllowedPublicSignalsPostPath,
} from "@/lib/security/public-signals-proxy";

describe("public signals proxy allowlist", () => {
  it("allows status evaluate history analytics and engine status", () => {
    expect(isAllowedPublicSignalsPath("/api/v1/signals/status")).toBe(true);
    expect(isAllowedPublicSignalsPath("/api/v1/signals/evaluate")).toBe(true);
    expect(isAllowedPublicSignalsPath("/api/v1/signals/history")).toBe(true);
    expect(isAllowedPublicSignalsPath("/api/v1/signals/analytics")).toBe(true);
    expect(isAllowedPublicSignalsPath("/api/v1/signals/engine/status")).toBe(true);
    expect(isAllowedPublicSignalsPath("/api/v1/signals/sync/status")).toBe(true);
    expect(
      isAllowedPublicSignalsPath(
        "/api/v1/signals/history/dec_0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      ),
    ).toBe(true);
  });

  it("allows engine start/stop POST only", () => {
    expect(isAllowedPublicSignalsPostPath("/api/v1/signals/engine/start")).toBe(true);
    expect(isAllowedPublicSignalsPostPath("/api/v1/signals/engine/stop")).toBe(true);
    expect(isAllowedPublicSignalsPostPath("/api/v1/signals/engine/status")).toBe(false);
    expect(isAllowedPublicSignalsPostPath("/api/v1/orders")).toBe(false);
  });

  it("blocks wallet and order paths", () => {
    expect(isAllowedPublicSignalsPath("/api/v1/exchange/wallet")).toBe(false);
    expect(isAllowedPublicSignalsPath("/api/v1/orders")).toBe(false);
    expect(isAllowedPublicSignalsPath("/api/v1/signals/execute")).toBe(false);
  });
});
