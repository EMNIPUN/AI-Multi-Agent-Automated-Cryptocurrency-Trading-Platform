# CryptoNova — Paper Equity Reconciliation (Prompt 66)

Currency: virtual **USDT**. All math uses `Decimal` (8-dp quantize).

---

## Distinctions

| Concept | Meaning |
| --- | --- |
| Signal hypothetical risk | `PaperRiskConfig.paper_balance` / `SignalRiskState` — **not** the broker ledger |
| Available balance | Free virtual cash |
| Reserved capital | Locked entry notional + entry fee for open longs |
| Realized PnL | Cumulative closed-trade net PnL |
| Unrealized PnL | Σ (mark − entry) × qty when marks exist |
| Cash total | `available + reserved` |
| Marked equity | Reconciled portfolio value when marks valid |
| Gross exposure (entry) | Σ qty × entry |
| Gross exposure (mark) | Σ qty × mark (only if all marks present) |

**Do not** equate `available + reserved` with marked equity when prices moved.

**Do not** substitute entry price for a missing mark.

---

## Formulas (spot-like unleveraged long)

### Flat

```
marked_equity = available + reserved
valuation = flat
```

### Open with valid marks

```
unrealized = Σ (mark − entry) × qty
marked_equity = available + reserved + unrealized
```

Entry fees already reduced `available` when the position opened; they are **not** subtracted again from equity.

### Missing / partial marks

```
marked_equity = None
valuation = unavailable | stale_or_partial
```

Portfolio entry sizing that requires equity capacity must return `DATA_UNAVAILABLE` — never invent capacity.

---

## Drawdown / daily loss denominators

- **Peak equity:** historical max marked equity (persisted).
- **Drawdown:** `(peak − current) / peak` (UTC timestamps on snapshots).
- **Daily loss:** `(day_start_equity − current) / day_start_equity` where `day_start` is first valid marked equity of the **UTC** calendar day.
- Halt is durable across process restart; a new UTC day rolls `day_start` but does **not** clear halt.
