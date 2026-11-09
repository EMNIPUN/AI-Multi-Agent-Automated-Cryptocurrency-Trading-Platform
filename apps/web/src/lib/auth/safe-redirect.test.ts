import { describe, expect, it } from "vitest";

import { isAuthPath, safeInternalPath } from "./safe-redirect";

describe("safeInternalPath", () => {
  it("allows relative app paths", () => {
    expect(safeInternalPath("/dashboard")).toBe("/dashboard");
    expect(safeInternalPath("/settings?tab=1")).toBe("/settings?tab=1");
  });

  it("blocks open redirects", () => {
    expect(safeInternalPath("https://evil.example")).toBe("/orchestrator");
    expect(safeInternalPath("//evil.example")).toBe("/orchestrator");
    expect(safeInternalPath("\\\\evil")).toBe("/orchestrator");
    expect(safeInternalPath("dashboard")).toBe("/orchestrator");
  });

  it("blocks auth loops", () => {
    expect(safeInternalPath("/login")).toBe("/orchestrator");
    expect(safeInternalPath("/signup")).toBe("/orchestrator");
  });

  it("uses fallback", () => {
    expect(safeInternalPath(null, "/markets")).toBe("/markets");
  });
});

describe("isAuthPath", () => {
  it("detects auth routes", () => {
    expect(isAuthPath("/login")).toBe(true);
    expect(isAuthPath("/forgot-password")).toBe(true);
    expect(isAuthPath("/dashboard")).toBe(false);
  });
});
