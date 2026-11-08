# CryptoNova — Paper Accounting Invariants (Prompt 65A)

All money math uses `Decimal` with 8-dp quantization (`ROUND_HALF_UP`).

---

## Cash identity

Let:

- `A` = available_balance  
- `R` = reserved_capital  
- `F` = fees_paid (cumulative fees, informational)  
- `P` = realized_pnl (cumulative net)  
- `B0` = initial_balance  

### Open long (entry fill)

```
reserve = entry_notional + entry_fee
A' = A − reserve
R' = R + reserve
F' = F + entry_fee
```

Constraints: `A' ≥ 0`, `R' ≥ 0`. Reject fill if `A < reserve`.

### Close long (exit fill)

```
net = (exit_fill − entry_fill) × qty − entry_fee − exit_fee
A' = A + reserve + net
R' = R − reserve   # floored at 0 defensively
F' = F + exit_fee
P' = P + net
```

Algebraic check after a full round-trip with no other activity:

```
A_final = B0 + net
R_final = 0
P_final = net
```

Fees are embedded in `net`; do **not** also subtract `F` from `A` a second time.

### Mark-to-market

Updates `mark_price` / `unrealized_pnl` on open positions only. Does **not** mutate `A`, `R`, or `P`.

---

## Portfolio guards (broker-side)

Independent of signal `risk_agent` veto:

- `max_open_positions`
- `max_total_exposure` (open + pending buy notional)
- insufficient funds
- no negative available
- no leverage / no shorts
- one open (or pending) position per symbol when configured
- reject non-positive quantity / non-finite prices
- require category string

Future Milestone 2 should feed reconciled paper equity/exposure into signal risk sizing; today’s hypothetical `paper_balance` in `RiskAssessment` is **not** this broker ledger.

---

## Idempotency keys

| Event | Unique key |
| --- | --- |
| Order per signal | `UNIQUE(session_id, source_signal_id, side)` |
| Entry fill | `fill_entry:{order_id}:{candle_start_ms}` + fill role unique |
| Position close | `pos_closed:{position_id}` |
| Candle | `candle:{symbol}:{interval}:{start_ms}` + cursor monotonic |

Failed SQLite transactions `ROLLBACK` — no partial balance/order/position writes.

---

## Restart

Re-open `PaperStore` on the same DB file restores sessions, open positions, balances, reserved capital, and candle cursor. Covered by `tests/test_core_paper_store.py::test_restart_recovery`.
