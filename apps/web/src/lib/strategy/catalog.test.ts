import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { STRATEGY_CATALOG, versionMatches } from "./catalog";

const CONFIG = path.resolve(__dirname, "../../../../../agent/multi_agent/config.py");

function field(src: string, name: string): string | null {
  const m = new RegExp(`^\\s*${name}\\s*(?::[^=]+)?=\\s*([^#\\n]+)`, "m").exec(src);
  return m ? m[1].trim() : null;
}

describe("strategy catalog stays in sync with agent/multi_agent/config.py", () => {
  const exists = fs.existsSync(CONFIG);
  it.skipIf(!exists)("matches the backend constants", () => {
    const src = fs.readFileSync(CONFIG, "utf8");
    const product = STRATEGY_CATALOG.find((s) => s.status === "product")!;
    expect(product.version).toBe(String(/STRATEGY_VERSION\s*=\s*"([^"]+)"/.exec(src)?.[1]));
    const weights = Object.fromEntries(product.agents.filter((a) => a.weight).map((a) => [a.id, a.weight]));
    for (const id of ["trend", "momentum", "volume", "structure"]) {
      expect(Number(weights[id])).toBe(Number(field(src, id)));
    }
    expect(field(src, "buy_threshold")).toBe("0.35");
    expect(field(src, "sell_threshold")).toBe("-0.35");
    expect(field(src, "min_market_quality")).toBe("1.0");
    expect(field(src, "min_confirmed_bars")).toBe("210");
    expect(field(src, "max_risk_fraction_per_trade")).toBe("0.01");
    expect(field(src, "min_stop_distance_pct")).toBe("0.004");
    expect(field(src, "max_stop_distance_pct")).toBe("0.03");
    expect(field(src, "take_profit_rr")).toBe("2.0");
    expect(field(src, "max_atr_pct")).toBe("0.06");
    expect(field(src, "daily_loss_halt_fraction")).toBe("0.03");
    expect(field(src, "agent_timeout_ms")).toBe("250");
    expect(field(src, "cooldown_ms")).toBe("15 * 60_000");
    expect(field(src, "lookback")).toBe("20");
    expect(field(src, "range_efficiency")).toBe("0.15");
    expect(field(src, "trend_efficiency")).toBe("0.35");
    expect(field(src, "minimum_supporting_agents")).toBe("2");
  });

  it("flags version mismatches only for the product strategy", () => {
    const [product, legacy] = STRATEGY_CATALOG;
    expect(versionMatches(product, product.version)).toBe(true);
    expect(versionMatches(product, "7.0.0")).toBe(false);
    expect(versionMatches(product, null)).toBeNull();
    expect(versionMatches(legacy, "6.0.0")).toBeNull();
  });
});
