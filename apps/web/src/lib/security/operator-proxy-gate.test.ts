import { describe, expect, it } from "vitest";

import { operatorLocalBrowserProxyEnabled } from "./operator-proxy-gate";

describe("operatorLocalBrowserProxyEnabled", () => {
  it("defaults to false / fail-closed", () => {
    expect(operatorLocalBrowserProxyEnabled({})).toBe(false);
    expect(operatorLocalBrowserProxyEnabled({ OPERATOR_LOCAL_BROWSER_PROXY_ENABLED: "" })).toBe(
      false,
    );
    expect(
      operatorLocalBrowserProxyEnabled({ OPERATOR_LOCAL_BROWSER_PROXY_ENABLED: "false" }),
    ).toBe(false);
  });

  it("requires explicit true", () => {
    expect(
      operatorLocalBrowserProxyEnabled({ OPERATOR_LOCAL_BROWSER_PROXY_ENABLED: "true" }),
    ).toBe(true);
  });
});
