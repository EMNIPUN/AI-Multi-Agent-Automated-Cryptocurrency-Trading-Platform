import { describe, expect, it } from "vitest";

import { mapAuthError } from "./map-auth-error";

describe("mapAuthError", () => {
  it("maps invalid credentials", () => {
    expect(mapAuthError({ message: "Invalid login credentials" })).toMatch(/incorrect/i);
  });

  it("never echoes raw unknown provider text as-is when generic", () => {
    const msg = mapAuthError({ message: "Something exotic from provider XYZ" });
    expect(msg).toBe("Authentication failed. Please try again.");
  });

  it("handles empty", () => {
    expect(mapAuthError(null)).toMatch(/failed/i);
  });
});
