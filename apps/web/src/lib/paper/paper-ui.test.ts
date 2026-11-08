import { describe, expect, it } from "vitest";

import { isSampleMetricLabel, resolvePaperUiMode } from "@/lib/paper/api";
import { isAllowedPublicPaperPath } from "@/lib/security/public-paper-proxy";

describe("paper UI mode", () => {
  it("loading", () => {
    expect(
      resolvePaperUiMode({
        loading: true,
        category: "spot",
        statusOk: true,
        enabled: true,
        apiError: false,
        sessionCount: 1,
      }),
    ).toBe("loading");
  });

  it("disabled", () => {
    expect(
      resolvePaperUiMode({
        loading: false,
        category: "spot",
        statusOk: true,
        enabled: false,
        apiError: false,
        sessionCount: 0,
      }),
    ).toBe("disabled");
  });

  it("no sessions", () => {
    expect(
      resolvePaperUiMode({
        loading: false,
        category: "spot",
        statusOk: true,
        enabled: true,
        apiError: false,
        sessionCount: 0,
      }),
    ).toBe("no_sessions");
  });

  it("unsupported futures", () => {
    expect(
      resolvePaperUiMode({
        loading: false,
        category: "linear",
        statusOk: true,
        enabled: true,
        apiError: false,
        sessionCount: 2,
      }),
    ).toBe("unsupported_futures");
  });

  it("unavailable api", () => {
    expect(
      resolvePaperUiMode({
        loading: false,
        category: "spot",
        statusOk: false,
        enabled: false,
        apiError: true,
        sessionCount: 0,
      }),
    ).toBe("unavailable");
  });

  it("ready", () => {
    expect(
      resolvePaperUiMode({
        loading: false,
        category: "spot",
        statusOk: true,
        enabled: true,
        apiError: false,
        sessionCount: 1,
      }),
    ).toBe("ready");
  });

  it("rejects SAMPLE labels as real metrics", () => {
    expect(isSampleMetricLabel("SAMPLE equity")).toBe(true);
    expect(isSampleMetricLabel("SIMULATED / PAPER ONLY")).toBe(false);
  });
});

describe("public paper proxy allowlist", () => {
  it("allows read paths only", () => {
    expect(isAllowedPublicPaperPath("/api/v1/paper/status")).toBe(true);
    expect(isAllowedPublicPaperPath("/api/v1/paper/sessions")).toBe(true);
    expect(isAllowedPublicPaperPath("/api/v1/paper/sessions/ps_test_65b")).toBe(true);
    expect(
      isAllowedPublicPaperPath("/api/v1/paper/sessions/ps_test_65b/account"),
    ).toBe(true);
    expect(
      isAllowedPublicPaperPath("/api/v1/paper/orders/by-signal/sig_api_1"),
    ).toBe(true);
  });

  it("rejects unrelated and mutation-looking paths", () => {
    expect(isAllowedPublicPaperPath("/api/v1/exchange/wallet")).toBe(false);
    expect(isAllowedPublicPaperPath("/api/v1/paper/sessions/../../etc")).toBe(false);
    expect(isAllowedPublicPaperPath("/api/v1/paper/orders")).toBe(false);
  });
});
