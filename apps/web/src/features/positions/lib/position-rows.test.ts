import { describe, expect, it } from "vitest";

import { filterRows, rowsFromReadApi, rowsFromSupervisorReport } from "./position-rows";

describe("position rows", () => {
  it("normalizes supervisor open positions and closed trades", () => {
    const rows = rowsFromSupervisorReport(
      {
        positions: [{ position_id: "p1", symbol: "HYPEUSDT", category: "linear", status: "OPEN", quantity: "0.05", entry_price: "65.1", mark_price: "65.9", stop_loss: "63", take_profit: "69", unrealized_pnl: "0.04", opened_ms: 10 }],
        recent_trades: [{ position_id: "p0", symbol: "HYPEUSDT", quantity: "0.05", entry_price: "60", exit_price: "61", realized_pnl: "0.05", exit_reason: "TAKE_PROFIT", opened_ms: 1, closed_ms: 5 }],
      },
      "ps_1",
    );
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ mode: "PAPER", source: "supervisor_journal", status: "OPEN", unrealized_pnl: "0.04", session_id: "ps_1" });
    expect(rows[1]).toMatchObject({ status: "CLOSED", realized_pnl: "0.05", exit_reason: "TAKE_PROFIT" });
  });
  it("hides stale marks from the read API and filters by status/market", () => {
    const rows = rowsFromReadApi([
      { position_id: "a", session_id: "s", symbol: "BTCUSDT", category: "spot", side: "LONG", status: "OPEN", quantity: "1", entry_price: "1", entry_fee: "0", stop_loss: null, take_profit: null, opened_ms: 1, closed_ms: null, exit_price: null, exit_fee: "0", exit_reason: null, realized_pnl: "0", mark_price: "2", unrealized_pnl: "1", unrealized_pnl_status: "unavailable", entry_signal_id: "sig", entry_order_id: "o", exit_order_id: null, data_label: "SIMULATED / PAPER ONLY", simulated: true },
    ]);
    expect(rows[0].mark_price).toBeNull();
    expect(rows[0].unrealized_pnl).toBeNull();
    expect(filterRows(rows, { status: "closed", market: "all", mode: "all" })).toHaveLength(0);
    expect(filterRows(rows, { status: "open", market: "spot", mode: "PAPER" })).toHaveLength(1);
    expect(filterRows(rows, { status: "all", market: "linear", mode: "all" })).toHaveLength(0);
  });
});
