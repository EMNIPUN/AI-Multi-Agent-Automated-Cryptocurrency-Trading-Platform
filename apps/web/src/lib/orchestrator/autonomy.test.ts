import { describe, expect, it } from "vitest";

import { allowedCommands, finiteNumber, formatMoney, scorePercent, sessionProgress, validateAuthorization, workerHealth, type SessionAuthorization, type SupervisorStatus } from "./autonomy";

const auth: SessionAuthorization = { symbol: "BTCUSDT", category: "linear", interval: "15", capital_usdt: "1000", risk_fraction: "0.01", duration_hours: 48 };

describe("autonomous session controls", () => {
  it("prevents restarting an active session and resuming a halted one", () => {
    expect(allowedCommands("RUNNING")).toEqual(["pause", "stop", "halt"]);
    expect(allowedCommands("PAUSED")).toContain("resume");
    expect(allowedCommands("HALTED")).not.toContain("resume");
    expect(allowedCommands("HALTED")).not.toContain("start");
    expect(allowedCommands("UNKNOWN")).toEqual([]);
  });

  it("accepts bounded paper authorization", () => {
    expect(validateAuthorization(auth)).toBeNull();
    expect(validateAuthorization({ ...auth, risk_fraction: "0.02", duration_hours: 168 })).toBeNull();
  });

  it.each([
    { risk_fraction: "0.0201" }, { risk_fraction: "0" }, { risk_fraction: "NaN" },
    { capital_usdt: "Infinity" }, { capital_usdt: "0" }, { capital_usdt: "1000001" },
    { duration_hours: 0 }, { duration_hours: 1.5 }, { duration_hours: 169 },
    { symbol: "../BTCUSDT" }, { symbol: "BTCUSD" }, { interval: "0" },
  ])("rejects out-of-bounds authorization %j", (override) => {
    expect(validateAuthorization({ ...auth, ...override })).not.toBeNull();
  });
});

describe("honest runtime and performance display", () => {
  it("does not turn missing or invalid financial values into zero", () => {
    for (const value of [null, undefined, "", true, false, "NaN", "Infinity"]) {
      expect(finiteNumber(value)).toBeNull();
      expect(formatMoney(value)).toBe("—");
    }
    expect(finiteNumber("0")).toBe(0);
  });

  it("does not display invalid strengths as probability-like percentages", () => {
    expect(scorePercent(undefined)).toBeNull();
    expect(scorePercent(1.3)).toBeNull();
    expect(scorePercent(-0.3)).toBeNull();
    expect(scorePercent(0.714)).toBe(71);
  });

  it("requires an observed recent heartbeat for a healthy worker", () => {
    const status: SupervisorStatus = { enabled: true, state: "RUNNING", mode: "PAPER", worker_running: true };
    expect(workerHealth(status, 500_000)).toBe("waiting");
    expect(workerHealth({ ...status, heartbeat_ms: 490_000 }, 500_000)).toBe("healthy");
    expect(workerHealth({ ...status, heartbeat_ms: 10_000 }, 500_000)).toBe("stale");
    expect(workerHealth({ ...status, heartbeat_ms: 600_000 }, 500_000)).toBe("stale");
    expect(workerHealth({ ...status, worker_running: false, heartbeat_ms: 490_000 }, 500_000)).toBe("offline");
  });

  it("clamps session progress and does not fabricate missing expiry", () => {
    expect(sessionProgress(auth, 3000)).toBeNull();
    const timed = { ...auth, started_at_ms: 1000, expires_at_ms: 3000 };
    expect(sessionProgress(timed, 2000)).toBe(50);
    expect(sessionProgress(timed, 500)).toBe(0);
    expect(sessionProgress(timed, 5000)).toBe(100);
  });
});
