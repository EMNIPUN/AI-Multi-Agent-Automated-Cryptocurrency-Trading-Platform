# Phase 1C — Persistent Risk State & Emergency Halt

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Scope | Durable account risk modes, daily loss halt, fail-closed equity |
| Constraints | Offline tests only; no live Bybit; no trading CLIs; no commit/push |
| Related | Phase 1A position safety, Phase 1B order idempotency |

---

## Root causes (pre-1C)

1. **In-memory `RiskState`** — daily halt cleared on every process restart.
2. **UTC/local inconsistency** — `date.today()` used local calendar, not UTC.
3. **Silent equity bypass** — `update_equity(None)` returned early, leaving prior in-memory state and allowing planning when equity was unknown.
4. **Day rollover wiped halt** — recreating `RiskState` on day change cleared `halted`.
5. **Sizing vs loss confusion** — `AGENT_RISK_PCT` (margin budget × leverage) was easy to confuse with `AGENT_DAILY_LOSS_PCT`.
6. **No integration** with Phase 1B unresolved intents at the risk-authorization layer (executor gated exposure, risk planner did not).

---

## Files created / modified

### Created
| File | Purpose |
|------|---------|
| `agent/risk_modes.py` | `NORMAL` / `REDUCE_ONLY` / `HALTED` / `RECOVERY_REQUIRED` |
| `agent/risk_store.py` | SQLite durable risk rows + CAS updates |
| `tests/test_persistent_risk.py` | Phase 1C offline coverage |
| `docs/implementation/PHASE_1C_PERSISTENT_RISK_REPORT.md` | This report |

### Modified
| File | Purpose |
|------|---------|
| `agent/risk.py` | Durable `RiskManager`, authorization APIs, operator recovery |
| `agent/runner.py` | Wire unresolved-intent checker; durable halt stop; recovery logging |

Strategy code, dry-run defaults, and mainnet live locks were not loosened.

---

## Risk state machine

| Mode | New exposure | Reduce-only plans | Notes |
|------|--------------|-------------------|-------|
| `NORMAL` | Allowed* | Allowed | *Requires confirmed equity + no unresolved intents |
| `REDUCE_ONLY` | Blocked | Allowed | Reserved / protective |
| `HALTED` | Blocked | Allowed by policy (runner stops loop) | Emergency; durable |
| `RECOVERY_REQUIRED` | Blocked | Allowed | Unknown equity, store faults, incidents |

\* Authorization also denied if Phase 1B unresolved intents exist.

**Strategies / LLMs cannot reset risk.** Only `attempt_operator_recovery()` with explicit ack + env token.

---

## Persistence design

- DB: `data/account_risk.sqlite3` (gitignored via `data/` + `*.sqlite3`).
- Unique key: `(env_scope, account_fp, risk_date)` where `risk_date` is **UTC** `YYYY-MM-DD`.
- Fields: start/latest equity, equity_confirmed, optional realized/unrealized PnL placeholders, daily loss threshold/current, emergency_halt, halt_reason, recovery_required, version, timestamps.
- **No API secrets** — `account_fp` is a hash fingerprint.
- Updates use **BEGIN IMMEDIATE** + **version CAS**.
- Restart **never overwrites** an existing day’s `start_equity` baseline.
- Corrupt/unavailable store → fail closed (`RECOVERY_REQUIRED` / halted view).

---

## Daily loss calculation

| Item | Definition |
|------|------------|
| Equity measure | Bybit UNIFIED wallet **`totalEquity`** via existing `get_equity()` |
| Includes | Mark-to-market equity (typically **includes unrealized** PnL) |
| Daily start | First **confirmed** `totalEquity` observed for that UTC date (persisted) |
| Daily loss % | `(start_equity - latest_equity) / start_equity * 100` |
| Breach | `daily_loss_pct_current >= AGENT_DAILY_LOSS_PCT` → `HALTED` + `emergency_halt` |
| Not this metric | `AGENT_RISK_PCT` = **per-trade sizing / margin budget** (× leverage on linear) |

### Limitations

- Separate realized vs unrealized streams from Bybit closed-PnL APIs are **not** fully integrated; columns exist but may remain null.
- If Bybit `totalEquity` is stale/wrong, risk inherits that limitation.
- No automatic cancel-all or flatten in this phase.

---

## UTC rollover policy

- Day boundary: **UTC midnight**.
- New UTC day → new row.
- If any prior row for the account has `emergency_halt=1`, the new day **starts `HALTED` / recovery_required** with prior reason — **does not silently clear**.
- Non-emergency days start `NORMAL` once equity is confirmed (or `RECOVERY_REQUIRED` while awaiting first equity).

---

## Recovery behavior (operator)

Manual procedure (no HTTP endpoint, no strategy hook):

1. Stop automated agent if running.
2. Verify exchange positions, open orders, and Phase 1B intent DB (`data/order_intents.sqlite3`) — clear or reconcile unresolved intents first.
3. Confirm UNIFIED equity on the intended environment (Testnet/Demo/Mainnet).
4. Set a local-only env var `AGENT_RISK_RECOVERY_TOKEN` to a strong random value (never commit it).
5. Call `RiskManager.attempt_operator_recovery` from a controlled offline/operator context with:
   - `acknowledge="I_ACKNOWLEDGE_ACCOUNT_VERIFIED"`
   - matching token
   - `verified_equity` from a trusted read
6. Recovery is **denied** if daily loss still breached, intents unresolved, ack/token wrong, or store unavailable.
7. **Process restart alone never re-enables** new entries while `emergency_halt` or `RECOVERY_REQUIRED` remains.

---

## Failure handling

| Failure | Behavior |
|---------|----------|
| Equity `None` / ≤0 | `equity_confirmed=False`; escalate to `RECOVERY_REQUIRED` (keep `HALTED` if emergency) |
| Risk DB error / CAS conflict | Fail closed; deny new exposure |
| Unresolved Phase 1B intents | Deny risk authorization for new exposure |
| Phase 1A position `UNKNOWN` | Still blocks planning (unchanged) |
| Runner sees `HALTED` | Journals kill switch and **stops** the loop |

---

## Offline tests and results

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --tb=line
```

| Result | **59 passed** (~2.5s), all mocked / local SQLite temp dirs |
|--------|------------------------------------------------------------|

Phase 1C cases covered: initial create, valid equity, equity failure, malformed/zero equity, daily loss breach, halt after restart, UTC rollover, emergency survives rollover, DB failure fail-closed, concurrent updates, unauthorized recovery, authorized recovery, Phase 1A UNKNOWN, Phase 1B unresolved intent, dry-run defaults, mainnet lock, no strategy reset API.

---

## Remaining risks / limitations

| Item | Notes |
|------|-------|
| No auto flatten/cancel-all | By design this phase |
| Fill advancement ACCEPTED→FILLED | Still Phase 1B follow-up |
| Forming-candle signals | Still open (signal quality) |
| Manual CLI risk path | Not on durable risk store |
| Operator recovery is code-callable | Token + ack required; still protect the token |
| `peak_equity` removed from active halt math | Daily loss vs start-of-day only |

---

## Recommended next milestone

**Phase 1D — Confirmed-bar signal gating** (ignore in-progress candles) and/or **fill evidence loop** to promote `ACCEPTED` → `FILLED`, plus an operator CLI that wraps recovery without exposing an unauthenticated network API.

---

## Acceptance criteria

| Criterion | Status |
|-----------|--------|
| Risk halt survives process restart | **Pass** |
| Unknown equity never authorizes new exposure | **Pass** |
| Daily rollover cannot silently remove emergency halt | **Pass** |
| Risk state not reset by strategy agents | **Pass** |
| Phase 1A / 1B properties intact | **Pass** (59 tests) |
| Offline only / no live exchange / no git push | **Pass** |

---

*End of Phase 1C report.*
