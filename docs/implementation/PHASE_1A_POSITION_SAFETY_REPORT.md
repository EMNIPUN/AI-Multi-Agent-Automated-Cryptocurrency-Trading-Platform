# Phase 1A — Fail-Closed Position Handling

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Scope | Agent position query + runner/risk fail-closed entry gating |
| Constraints | Offline tests only; no `main.py` / `run_agent.py` / `test_connection.py`; no live Bybit calls; no commit/push |
| Related | `CURRENT_REPOSITORY_AUDIT.md`, `docs/architecture/REPOSITORY_STRUCTURE.md`, `docs/PHASE_0_REPOSITORY_SAFETY_REPORT.md` |

---

## Root cause

`get_position()` previously returned `dict | None` and mapped timeouts, API errors, and malformed payloads to `None` via broad exception handlers.

`AgentRunner` / `RiskManager.plan_trade` treated falsy/`None` as **confirmed flat**, so a failed position read could authorize a new entry while an open position still existed.

---

## Design decisions

1. **Explicit tri-state** — `PositionStatus` / `PositionSnapshot`:
   - `FLAT` — successful Bybit response explicitly confirms no open size
   - `OPEN` — successful response with validated size/side
   - `UNKNOWN` — failures, auth/API errors, timeouts, malformed/ambiguous data
2. **Only `FLAT` authorizes new exposure.** `UNKNOWN` is never treated as flat.
3. **Reduce-only only with confirmed `OPEN`.** Without size/side, closing is unsafe; runner journals a structured block and skips planning.
4. **Occupancy** counts `OPEN` and `UNKNOWN` toward `max_open_positions` (UNKNOWN may already be exposure).
5. **Minimal change** — strategy entry rules untouched; dry-run default and mainnet `AGENT_ALLOW_LIVE` lock unchanged.
6. **No credential logging** — reasons use exception types / `retCode` + `retMsg` only.

---

## Files changed (implementation)

| File | Change |
|------|--------|
| `agent/market_data.py` | `PositionStatus`, `PositionSnapshot`; fail-closed `get_position` (linear + spot) |
| `agent/risk.py` | Snapshot-aware `plan_trade` / `open_position_count`; block opens on `UNKNOWN` |
| `agent/runner.py` | Journal/display `UNKNOWN`; skip `plan_trade`/`execute` when unknown |
| `requirements-dev.txt` | `pytest` (+ runtime deps via `-r requirements.txt`) |
| `tests/conftest.py` | `make_settings` helper |
| `tests/test_get_position.py` | Mocked FLAT / OPEN / UNKNOWN / malformed / timeout cases |
| `tests/test_risk_position_fail_closed.py` | Risk entry blocking + reduce-only on OPEN |
| `tests/test_runner_position_unknown.py` | Runner blocks entries and journals |
| `docs/implementation/PHASE_1A_POSITION_SAFETY_REPORT.md` | Canonical report (this file) |

**Not modified for this objective:** `ema_rsi.py` strategy rules, executor placement mechanics, `bot/` CLI trading, env defaults.

---

## Tests executed and results

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --tb=short
```

| Result | Detail |
|--------|--------|
| **24 passed** | ~0.27s |
| Exchange I/O | Fully mocked (`MagicMock`) — no Bybit contact |
| Live CLIs | Not executed |

| Requirement case | Coverage |
|------------------|----------|
| FLAT (valid empty / zero size) | `test_get_position.py` |
| OPEN (linear + spot inventory) | `test_get_position.py`, risk close path |
| UNKNOWN (timeout, API error, auth-style retCode) | `test_get_position.py` |
| Malformed / missing data | `test_get_position.py` |
| Runner entry blocking | `test_runner_position_unknown.py` |
| Risk blocks new entry on UNKNOWN | `test_risk_position_fail_closed.py` |

Safety defaults checked via `load_settings()` in this verification: `dry_run=True`, `allow_live=False` (with current local env / code defaults).

---

## Acceptance criteria

| Criterion | Status |
|-----------|--------|
| Failed position reads never treated as FLAT | **Pass** |
| UNKNOWN blocks all new entries | **Pass** |
| Confirmed OPEN handled (including reduce-only close path) | **Pass** |
| Dry-run / mainnet safety defaults unchanged | **Pass** |
| Offline tests pass | **Pass** (24) |

---

## Remaining gaps

| Gap | Notes |
|-----|-------|
| Manual CLI `bot/trading.py` position helpers | Still separate; not fail-closed to the same contract |
| `get_equity` / price helpers | Still soft-fail to `None` (out of Phase 1A scope) |
| Order idempotency (`orderLinkId`) | Not done — Phase 1B |
| Persisted daily halt | Still in-memory |
| Forming-candle signals | Unchanged |
| UNKNOWN cannot auto-flatten | By design until OPEN is confirmed |
| Spot dust (`walletBalance > 0`) counts as OPEN | Pre-existing semantics |

---

## Recommended next step

**Phase 1B — Order idempotency:** stable `orderLinkId` on agent orders and safer retry policy for market IOC placements.
