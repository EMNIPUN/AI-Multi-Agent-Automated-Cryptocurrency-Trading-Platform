import { describe, expect, it } from "vitest";

import { estimateCandleCount, resolveBacktestUiMode } from "@/lib/backtest/api";
import {
  ADVISORY_UNCHANGED_LABEL,
  HISTORICAL_SIM_LABEL,
  SIM_LABEL,
  asOptionalMetric,
  assertNoFixturePayload,
  formatDecimalDisplay,
  formatOptionalMetric,
  shadowComparisonAllowed,
} from "@/lib/backtest/format";
import {
  isAllowedPublicBacktestPath,
  isAllowedPublicBacktestPostPath,
} from "@/lib/security/public-backtest-proxy";

describe("backtest UI helpers", () => {
  it("labels simulation clearly and rejects sample fixture payloads", () => {
    expect(SIM_LABEL).toContain("HISTORICAL SIMULATION");
    expect(SIM_LABEL).toContain("NOT LIVE");
    expect(assertNoFixturePayload(SIM_LABEL)).toBe(true);
    expect(HISTORICAL_SIM_LABEL).toBe("Historical Simulation — Not Live Trading");
    expect(ADVISORY_UNCHANGED_LABEL).toBe("Advisory Only — Trading Decisions Unchanged");
    expect(shadowComparisonAllowed("complete")).toBe(true);
    expect(shadowComparisonAllowed("incomplete")).toBe(false);
    expect(shadowComparisonAllowed(undefined)).toBe(false);
  });

  it("formats optional metrics without inventing 0%", () => {
    expect(
      formatOptionalMetric(asOptionalMetric({ value: null, status: "empty" })),
    ).toBe("n/a (no closed trades)");
    expect(
      formatOptionalMetric(
        asOptionalMetric({ value: null, status: "unbounded", reason: "no_losses" }),
      ),
    ).toBe("unbounded");
    expect(formatDecimalDisplay("NaN")).toBe("unavailable");
    expect(formatDecimalDisplay("12.5", { suffix: "USDT" })).toBe("12.5 USDT");
  });

  it("resolves UI modes for disabled/empty/ready", () => {
    expect(resolveBacktestUiMode({ enabled: false } as never)).toBe("disabled");
    expect(resolveBacktestUiMode(null, 503)).toBe("disabled");
    expect(resolveBacktestUiMode(null, 0)).toBe("unreachable");
    expect(
      resolveBacktestUiMode({
        enabled: true,
        results_dir_exists: false,
        run_count: 0,
      } as never),
    ).toBe("missing_dir");
    expect(
      resolveBacktestUiMode({
        enabled: true,
        results_dir_exists: true,
        run_count: 0,
      } as never),
    ).toBe("empty");
    expect(
      resolveBacktestUiMode({
        enabled: true,
        results_dir_exists: true,
        run_count: 2,
      } as never),
    ).toBe("ready");
  });

  it("allowlists backtest read + gated run paths", () => {
    expect(isAllowedPublicBacktestPath("/api/v1/backtests/status")).toBe(true);
    expect(isAllowedPublicBacktestPath("/api/v1/backtests/runs")).toBe(true);
    expect(isAllowedPublicBacktestPath("/api/v1/backtests/run-capabilities")).toBe(
      true,
    );
    expect(isAllowedPublicBacktestPath("/api/v1/backtests/shadow-status")).toBe(true);
    expect(
      isAllowedPublicBacktestPath("/api/v1/backtests/runs/bt_0123456789abcdef"),
    ).toBe(true);
    expect(
      isAllowedPublicBacktestPath(
        "/api/v1/backtests/runs/bt_0123456789abcdef/metrics",
      ),
    ).toBe(true);
    expect(
      isAllowedPublicBacktestPath(
        "/api/v1/backtests/runs/bt_0123456789abcdef/orders",
      ),
    ).toBe(true);
    expect(
      isAllowedPublicBacktestPath(
        "/api/v1/backtests/runs/bt_0123456789abcdef/status",
      ),
    ).toBe(true);
    expect(
      isAllowedPublicBacktestPath("/api/v1/backtests/jobs/btj_0123456789abcdef"),
    ).toBe(true);
    expect(isAllowedPublicBacktestPath("/api/v1/backtests/runs/../etc/passwd")).toBe(
      false,
    );
    expect(isAllowedPublicBacktestPath("/api/v1/paper/sessions")).toBe(false);
    expect(isAllowedPublicBacktestPath("/api/v1/backtests/execute")).toBe(false);
    expect(isAllowedPublicBacktestPostPath("/api/v1/backtests/runs")).toBe(true);
    expect(isAllowedPublicBacktestPostPath("/api/v1/backtests/status")).toBe(false);
    expect(isAllowedPublicBacktestPostPath("/api/v1/backtests/jobs/btj_abc")).toBe(
      false,
    );
  });

  it("estimates candle counts for date validation", () => {
    const start = 1_700_000_000_000;
    const end = start + 15 * 60_000 * 99;
    expect(estimateCandleCount(start, end, "15")).toBe(100);
    expect(estimateCandleCount(end, start, "15")).toBe(0);
  });
});
