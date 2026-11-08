import { describe, expect, it } from "vitest";

import {
  assertNoFixturePayload,
  buildAnalyticsQuery,
  formatDecimalDisplay,
  formatOptionalMetric,
  signedMoneyClass,
  tradeOutcome,
  validateExitDateRange,
} from "@/lib/paper/analytics-format";
import { isAllowedPublicPaperPath } from "@/lib/security/public-paper-proxy";

describe("analytics formatting", () => {
  it("preserves decimal strings and rejects NaN/Infinity tokens", () => {
    expect(formatDecimalDisplay("12.34000000", { suffix: "USDT" })).toBe(
      "12.34000000 USDT",
    );
    expect(formatDecimalDisplay("NaN")).toBe("unavailable");
    expect(formatDecimalDisplay("Infinity")).toBe("unavailable");
    expect(formatDecimalDisplay(null)).toBe("unavailable");
  });

  it("handles optional metric statuses without inventing 0%", () => {
    expect(
      formatOptionalMetric({ value: null, status: "empty", reason: "no_closed_trades" }),
    ).toBe("n/a (no closed trades)");
    expect(
      formatOptionalMetric({
        value: null,
        status: "unbounded",
        reason: "no_losing_trades_positive_profit",
      }),
    ).toBe("unbounded");
    expect(
      formatOptionalMetric({ value: null, status: "unavailable", reason: "no_winners" }),
    ).toContain("unavailable");
    expect(
      formatOptionalMetric({ value: "40.00000000", status: "available", reason: null }, {
        suffix: "%",
      }),
    ).toBe("40.00000000 %");
  });

  it("classifies outcomes and signed money classes", () => {
    expect(tradeOutcome("1.5")).toBe("win");
    expect(tradeOutcome("-0.2")).toBe("loss");
    expect(tradeOutcome("0")).toBe("breakeven");
    expect(signedMoneyClass("2")).toContain("emerald");
    expect(signedMoneyClass("-2")).toContain("rose");
  });
});

describe("analytics filters", () => {
  it("builds supported query params", () => {
    const q = buildAnalyticsQuery({
      symbol: "BTCUSDT",
      exitFromMs: 1000,
      exitToMs: 2000,
      limit: 25,
      offset: 50,
      series: "marked",
    });
    expect(q).toContain("symbol=BTCUSDT");
    expect(q).toContain("exit_from_ms=1000");
    expect(q).toContain("exit_to_ms=2000");
    expect(q).toContain("limit=25");
    expect(q).toContain("offset=50");
    expect(q).toContain("series=marked");
  });

  it("rejects invalid date ranges", () => {
    expect(validateExitDateRange("2026-11-08", "2026-11-07").ok).toBe(false);
    expect(validateExitDateRange("bad", "").ok).toBe(false);
    const ok = validateExitDateRange("2026-11-01", "2026-11-08");
    expect(ok.ok).toBe(true);
    if (ok.ok) {
      expect(ok.fromMs).toBe(Date.UTC(2026, 10, 1, 0, 0, 0, 0));
      expect(ok.toMs).toBe(Date.UTC(2026, 10, 8, 23, 59, 59, 999));
    }
  });

  it("does not treat analytics payloads as fixtures", () => {
    expect(
      assertNoFixturePayload({
        data_label: "SIMULATED / PAPER ONLY",
        closed_trades: 0,
        win_rate_pct: { status: "empty", value: null },
      }),
    ).toBe(true);
  });
});

describe("analytics proxy allowlist", () => {
  it("allows analytics GET paths", () => {
    expect(
      isAllowedPublicPaperPath("/api/v1/paper/sessions/ps_abc/analytics"),
    ).toBe(true);
    expect(
      isAllowedPublicPaperPath("/api/v1/paper/sessions/ps_abc/analytics/trades"),
    ).toBe(true);
    expect(
      isAllowedPublicPaperPath("/api/v1/paper/sessions/ps_abc/analytics/equity"),
    ).toBe(true);
    expect(
      isAllowedPublicPaperPath("/api/v1/paper/sessions/ps_abc/analytics/symbols"),
    ).toBe(true);
  });
});
