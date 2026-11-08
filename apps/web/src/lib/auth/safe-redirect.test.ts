import { describe, expect, it } from "vitest";

import { isAuthPath, safeInternalPath } from "./safe-redirect";

describe("safeInternalPath", () => {
  it("allows relative app paths", () => {
    expect(safeInternalPath("/dashboard")).toBe("/dashboard");
    expect(safeInternalPath("/settings?tab=1")).toBe("/settings?tab=1");
  });

  it("blocks open redirects", () => {
    expect(safeInternalPath("https://evil.example")).toBe("/dashboard");
    expect(safeInternalPath("//evil.example")).toBe("/dashboard");
    expect(safeInternalPath("\\\\evil")).toBe("/dashboard");
    expect(safeInternalPath("dashboard")).toBe("/dashboard");
  });

  it("blocks auth loops", () => {
    expect(safeInternalPath("/login")).toBe("/dashboard");
    expect(safeInternalPath("/signup")).toBe("/dashboard");
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
