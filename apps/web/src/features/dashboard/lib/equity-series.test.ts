import { describe, expect, it } from "vitest";

import { realizedEquitySeries } from "./equity-series";

describe("realizedEquitySeries", () => {
  it("returns an empty series without trades or initial balance", () => {
    expect(realizedEquitySeries(null)).toEqual([]);
    expect(realizedEquitySeries({ initial_balance: "100", recent_trades: [] })).toEqual([]);
    expect(realizedEquitySeries({ recent_trades: [{ position_id: "p", symbol: "X", quantity: "1", entry_price: "1", exit_price: "2", realized_pnl: "1", exit_reason: "TP", opened_ms: 1, closed_ms: 2 }] })).toEqual([]);
  });
  it("accumulates realized pnl in close order starting from the initial balance", () => {
    const series = realizedEquitySeries({
      initial_balance: "1000",
      recent_trades: [
        { position_id: "b", symbol: "HYPEUSDT", quantity: "1", entry_price: "1", exit_price: "2", realized_pnl: "-5.5", exit_reason: "STOP_LOSS", opened_ms: 50, closed_ms: 200 },
        { position_id: "a", symbol: "HYPEUSDT", quantity: "1", entry_price: "1", exit_price: "2", realized_pnl: "12.25", exit_reason: "TAKE_PROFIT", opened_ms: 10, closed_ms: 100 },
      ],
    });
    expect(series.map((p) => [p.t, p.value])).toEqual([
      [10, 1000],
      [100, 1012.25],
      [200, 1006.75],
    ]);
  });
});
