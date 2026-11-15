import { describe, expect, it } from "vitest";

import { decimalTone, formatDecimal, formatMoney, formatPrice, formatQuantity, parseDecimal } from "./decimal";
import { explainReason, explainReasons, primaryReason } from "./reason-codes";
import { normalizeStatus } from "./status";
import { formatDuration, formatRelative, intervalLabel } from "./time";

describe("decimal formatting", () => {
  it("keeps string precision without float loss", () => {
    expect(formatDecimal("12345678.12345678")).toBe("12,345,678.12345678");
    expect(formatQuantity("0.00000123")).toBe("0.00000123");
    expect(formatQuantity("1.50000000")).toBe("1.5");
  });
  it("rounds half-up on the string with carry", () => {
    expect(formatMoney("1.005")).toBe("1.01");
    expect(formatMoney("9.999")).toBe("10.00");
    expect(formatMoney("-0.004")).toBe("0.00");
  });
  it("handles signs, zero, and invalid input", () => {
    expect(formatDecimal("-1234.5", { digits: 2 })).toBe("-1,234.50");
    expect(formatDecimal("12.5", { digits: 1, sign: true })).toBe("+12.5");
    expect(formatDecimal("0.000", { digits: 2, sign: true })).toBe("0.00");
    expect(formatDecimal(null)).toBe("—");
    expect(formatDecimal("abc", { fallback: "n/a" })).toBe("n/a");
    expect(formatDecimal(Number.NaN)).toBe("—");
  });
  it("picks price precision by magnitude", () => {
    expect(formatPrice("65432.1")).toBe("65,432.1");
    expect(formatPrice("65.8831")).toBe("65.8831");
    expect(formatPrice("0.123456")).toBe("0.123456");
  });
  it("derives tone from sign only", () => {
    expect(decimalTone("12")).toBe("profit");
    expect(decimalTone("-0.01")).toBe("loss");
    expect(decimalTone("0.00")).toBe("neutral");
    expect(decimalTone(null)).toBe("neutral");
    expect(parseDecimal("-0")?.negative).toBe(false);
  });
});

describe("reason codes", () => {
  it("explains known codes and humanizes unknown ones", () => {
    expect(explainReason("TREND_CONFLICT_VETO").severity).toBe("block");
    expect(explainReason("made_up_code").title).toBe("Made Up Code");
  });
  it("dedupes and ranks by severity", () => {
    const list = explainReasons(["RISK_OK", "RISK_OK", "COOLDOWN_ACTIVE"]);
    expect(list).toHaveLength(2);
    expect(primaryReason(["RISK_OK", "DAILY_LOSS_LIMIT"])?.code).toBe("DAILY_LOSS_LIMIT");
    expect(primaryReason([])).toBeNull();
  });
});

describe("status normalization", () => {
  it("maps backend words to canonical kinds", () => {
    expect(normalizeStatus("RUNNING")).toBe("running");
    expect(normalizeStatus("active")).toBe("running");
    expect(normalizeStatus("HALTED")).toBe("blocked");
    expect(normalizeStatus("ERROR")).toBe("failed");
    expect(normalizeStatus("")).toBe("unknown");
    expect(normalizeStatus(true)).toBe("ok");
  });
});

describe("time formatting", () => {
  it("formats relative and durations", () => {
    const now = 1_000_000_000;
    expect(formatRelative(now - 2_000, now)).toBe("just now");
    expect(formatRelative(now - 90_000, now)).toBe("2m ago");
    expect(formatRelative(now + 300_000, now)).toBe("in 5m");
    expect(formatRelative(null, now)).toBe("—");
    expect(formatDuration(3_725_000)).toBe("1h 2m");
    expect(intervalLabel("15")).toBe("15m");
    expect(intervalLabel("240")).toBe("4H");
    expect(intervalLabel("D")).toBe("1D");
  });
});
