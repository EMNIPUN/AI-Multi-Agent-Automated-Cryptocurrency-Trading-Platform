# CryptoNova — Paper Analytics Metric Definitions (67A)

| Field | Value |
| --- | --- |
| Scope | Local paper journal only (Spot-like unleveraged longs) |
| Source of truth | `paper_positions` CLOSED rows + `paper_equity_snapshots` |
| Label | SIMULATED / PAPER ONLY — not live account performance |

---

## Closed trade

A completed trade is a `paper_positions` row with `status=CLOSED`, non-null `exit_price` and `closed_ms`.

- Open positions are **excluded**.
- Unfilled BUY signals are **not** trades.
- Time-range membership uses **exit timestamp** (`closed_ms`, UTC ms).

### Per-trade fields

| Field | Definition |
| --- | --- |
| Gross realized PnL | `(exit_price − entry_price) × quantity` |
| Entry / exit fees | Persisted `entry_fee` / `exit_fee` |
| Net realized PnL | Authoritative `position.realized_pnl` (broker `long_net_pnl` = gross − entry_fee − exit_fee) |

**Fee rule:** do **not** subtract fees again from net. Gross is recomputed for disclosure; net is never re-derived by subtracting fees from an already-net journal value.

---

## Outcome classification

| Class | Rule |
| --- | --- |
| Winning | `net_realized_pnl > 0` |
| Losing | `net_realized_pnl < 0` |
| Breakeven | `net_realized_pnl == 0` |

---

## Aggregate trade metrics

| Metric | Formula | Empty / edge |
| --- | --- | --- |
| Win rate % | `winning / total_closed × 100` | Breakeven **included** in denominator. Empty → status `empty` |
| Gross profit | `sum(positive net)` | `0` when none |
| Gross loss | `abs(sum(negative net))` | `0` when none |
| Net realized PnL | `sum(all net)` | `0` when empty set of trades |
| Total fees / fee drag | `sum(entry_fee + exit_fee)` | |
| Profit factor | `gross_profit / gross_loss` | No trades → `empty`. Loss=0 & profit>0 → `unbounded` (no Infinity). Both 0 → `unavailable` |
| Average win | `gross_profit / winners` | No winners → unavailable |
| Average loss | `gross_loss / losers` | No losers → unavailable |
| Expectancy | `net / total_closed` | Empty → empty. Cross-check: `p_win×avg_win − p_loss×avg_loss` (BE contribute 0) |
| Realized return % | `net / initial_session_balance × 100` | **Realized-only**; excludes unrealized open PnL |
| Best / worst | max / min net | Empty → empty |
| Avg holding ms | mean(`closed_ms − opened_ms`) | |

Optional R-multiple is **not** computed unless durable original entry risk is present and trustworthy (not reconstructed from current config).

---

## Equity series (do not mix)

| Series | Source | Notes |
| --- | --- | --- |
| Realized balance | Snapshot `available_balance + reserved_capital` | Cash ledger view |
| Marked equity | Snapshot `marked_equity` when valuation usable | Requires valid marks; skips unavailable / invalid |

No interpolation of missing intermediate points. Sparse observations may understate intraperiod drawdown — disclosed via warnings.

---

## Maximum drawdown

On one clearly labeled series:

```
running_peak = max(prev_peak, equity)
drawdown_pct = (running_peak − equity) / running_peak × 100
```

Returns max % and amount, peak/trough timestamps, observation count, series type, sparse warning.

- Realized-balance DD is labeled **Maximum observed realized-balance drawdown**.
- Marked DD is labeled **Maximum observed marked-equity drawdown**.
- Never mixes series types.

---

## Filters

- Session isolation: one virtual session at a time for equity curves.
- Symbol filter: closed positions for that symbol.
- Date range: UTC ms on **exit** time.
- Cross-session trade rollups (if ever added) must be labeled aggregated trade stats, not single-account return.

---

## Availability statuses

`available` | `unavailable` | `unbounded` | `empty`

JSON never emits NaN or Infinity.
