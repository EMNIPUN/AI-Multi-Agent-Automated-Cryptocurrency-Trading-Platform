# CryptoNova — Portfolio Risk Contract (Prompt 66)

| Field | Value |
| --- | --- |
| Module | `agent/paper/risk.py`, `equity.py`, `risk_config.py`, `portfolio.py` |
| Default wiring | **OFF** (`PAPER_PORTFOLIO_RISK_ENABLED=False`, broker `portfolio_risk=None`) |
| Scope | Spot-like unleveraged **LONG** only |

---

## Two-stage gate

1. **Signal risk** (`evaluate_signal_risk`) — hypothetical; VETO/BLOCKED/HALTED authoritative.
2. **Portfolio risk** (`evaluate_portfolio_entry`) — reconciled paper ledger; additional gate only.

A VETOED signal must never become APPROVED via portfolio risk (`submit_decision_with_portfolio_risk`).

---

## Verdicts

`APPROVED` | `REJECTED` | `HALTED` | `DATA_UNAVAILABLE`

### Selected reason codes

`PORTFOLIO_HALTED`, `DAILY_LOSS_LIMIT`, `MAX_DRAWDOWN_LIMIT`, `MAX_OPEN_POSITIONS`, `MAX_EXPOSURE`, `SYMBOL_ALREADY_OPEN`, `INSUFFICIENT_FUNDS`, `ZERO_QUANTITY`, `NET_RR_BELOW_MIN`, `UNSUPPORTED_CATEGORY`, `MARKS_UNAVAILABLE`, `INVALID_PRICE`, `NON_POSITIVE_STOP_RISK`, `SIGNAL_RISK_VETO_AUTHORITATIVE`

---

## Configuration defaults (paper-only)

| Knob | Default | Denominator |
| --- | --- | --- |
| max risk / trade | 1% | marked equity |
| max open positions | 3 | count |
| max gross exposure | 60% | marked equity |
| max daily loss | 3% | UTC day-start marked equity |
| max drawdown | 10% | peak marked equity |
| min net RR | 1.5 | net reward / net risk after fees+slip |
| fee / slip | match broker (0.001 / 5 bps) | — |

Stop loss is **modeled**, not a guaranteed maximum loss (gaps/slippage).

Sizing takes the **minimum** of risk, cash, and exposure caps; floors quantity (never rounds up); may resize requested notional **down**.

---

## Halt vs exits

New BUY entries blocked when halted. SELL (risk-reducing close) remains eligible.

---

## Persistence (schema v2)

- `paper_risk_state` — halted, peak, day_start, day_key
- `paper_equity_snapshots` — valuation trail
- v1 DBs migrate additively; sessions preserved

Atomic fill path rechecks halt + max positions inside `BEGIN IMMEDIATE`.
