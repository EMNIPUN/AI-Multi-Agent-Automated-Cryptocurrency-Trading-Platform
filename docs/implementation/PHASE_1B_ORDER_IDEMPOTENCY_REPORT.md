# Phase 1B — Order Idempotency & Durable Intent Processing

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Scope | Automated agent order submission safety (idempotent intents) |
| Constraints | Offline tests only; no live Bybit; no CLI trading scripts; no commit/push |
| Related | `CURRENT_REPOSITORY_AUDIT.md`, Phase 1A position safety report |

---

## Root cause

Automated `OrderExecutor.execute()` called `session.place_order` **without** a client `orderLinkId`, while `bot.client.create_session()` enabled `force_retry=True` / `max_retries=5`.

A timeout after the exchange accepted an order, followed by a pybit retry (or a later agent tick re-planning the same signal), could create **duplicate market IOC exposure**. Process crashes mid-submit left no durable record to reconcile.

This phase does **not** claim exactly-once exchange execution — it claims **at-most-one local submission attempt per durable intent**, with fail-closed handling when the result is ambiguous.

---

## Task A — Order submission audit

| Pathway | Mechanism | Retry risk |
|---------|-----------|------------|
| Agent live path | `OrderExecutor` → `place_order` | **Was high** (session retries + no link id) |
| Agent dry-run | Journal only | No exchange write |
| Manual CLI | `bot/trading.py` via `call_api(..., retries=3)` | **Still present** (out of scope) |

**pybit:** `force_retry=True` retries network/timeouts; unsafe for non-idempotent creates.

**Repeated ticks:** Same signal/plan could call `place_order` again with a fresh request.

**Manual CLI risks (not addressed):** interactive `place_order` / cancel paths still use retrying `call_api`; no intent store; mainnet confirm only.

---

## Architecture changes

```text
TradePlan
  → build OrderIntent (stable orderLinkId)
  → SQLite IntentStore.insert_created  (BEFORE network)
  → dry-run: mark CANCELED (not FILLED), journal dry_run
  → live: claim CREATED→SUBMISSION_PENDING
  → create_write_session() single attempt place_order(orderLinkId=...)
  → ACCEPTED | REJECTED | RECONCILIATION_REQUIRED
  → unresolved intents block new exposure-increasing orders
  → restart: SUBMISSION_PENDING/UNKNOWN → RECONCILIATION_REQUIRED
```

Read sessions may still retry; **writes** use `create_write_session()` (`force_retry=False`, `max_retries=1`).

---

## Files created / modified

### Created
| File | Role |
|------|------|
| `agent/order_ids.py` | Fingerprint + Bybit-safe `orderLinkId` |
| `agent/order_intent.py` | Intent model + state machine |
| `agent/intent_store.py` | SQLite persistence + unique constraint |
| `agent/reconcile.py` | orderLinkId reconciliation (fail-closed) |
| `tests/test_order_idempotency.py` | Phase 1B offline coverage |
| `docs/implementation/PHASE_1B_ORDER_IDEMPOTENCY_REPORT.md` | This report |

### Modified
| File | Role |
|------|------|
| `agent/executor.py` | Intent-first execution; no blind retry |
| `agent/runner.py` | Restart recovery + reconcile before ticks |
| `agent/risk.py` | Optional `correlation_id` / `risk_auth_ref` on `TradePlan` |
| `bot/client.py` | `create_session` knobs + `create_write_session` |
| `.gitignore` | Ignore `data/` |

**Unchanged by design:** strategy rules, dry-run / mainnet live defaults, root entry points, manual CLI trading logic.

---

## Order state machine

States: `CREATED`, `SUBMISSION_PENDING`, `ACCEPTED`, `PARTIALLY_FILLED`, `FILLED`, `REJECTED`, `CANCELED`, `UNKNOWN`, `RECONCILIATION_REQUIRED`.

| From | To (examples) |
|------|----------------|
| CREATED | SUBMISSION_PENDING, CANCELED (dry-run), REJECTED |
| SUBMISSION_PENDING | ACCEPTED, REJECTED, UNKNOWN, RECONCILIATION_REQUIRED |
| UNKNOWN | RECONCILIATION_REQUIRED, ACCEPTED/FILLED/… (after proof) |
| RECONCILIATION_REQUIRED | proven terminal / ACCEPTED / PARTIAL / UNKNOWN |
| ACCEPTED | PARTIALLY_FILLED, FILLED, CANCELED |

**Ack ≠ fill:** `retCode==0` with `orderId` → `ACCEPTED` only.

**Restart:** in-flight live intents → `RECONCILIATION_REQUIRED` (never auto-resubmit).

---

## Persistence design

- Engine: **SQLite** at `data/order_intents.sqlite3` (gitignored).
- Unique key: `(env_scope, account_fp, client_order_id)`.
- `account_fp`: SHA-256 fingerprint of API key material (not the secret).
- `env_scope`: `testnet` / `demo` / `mainnet`.
- Persist **CREATED** before network I/O; claim uses `BEGIN IMMEDIATE`.
- No API secrets in the DB.

---

## Retry policy

| Operation | Policy |
|-----------|--------|
| `place_order` | **One attempt** via write session; no automatic resubmit |
| Same intent re-entry | Idempotent skip / reconcile only |
| Timeout / network / malformed ack | `UNKNOWN` → `RECONCILIATION_REQUIRED` |
| Reads (`get_positions`, klines, reconcile lookups) | Existing read session retries OK |

**Never** treat timeout as proof the order failed.

---

## Reconciliation behavior

Lookups by `orderLinkId` across open orders, order history, and executions.

| Outcome | Action |
|---------|--------|
| Strong match (status mapped) | Transition to ACCEPTED / PARTIAL / FILLED / … |
| Executions without full order row | PARTIALLY_FILLED (conservative proof of activity) |
| No match | **Inconclusive** — remain unresolved (does **not** mean “never submitted”) |
| Lookup errors | Prefer UNKNOWN / keep RECONCILIATION_REQUIRED |

While unresolved live intents exist, **new exposure-increasing** executes are blocked (incident journaled).

---

## Dry-run compatibility

- Default `AGENT_DRY_RUN=true` unchanged.
- Dry-run persists intent then moves to `CANCELED` with `dry_run_not_submitted`.
- Journal event remains `dry_run` with `not_filled` detail.
- Never reports dry-run as `FILLED` / exchange `order`.

---

## Tests executed

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --tb=line
```

| Result | **42 passed** (~1.5s), offline mocks only |
|--------|--------------------------------------------|

Coverage includes: ID validation, repeat/concurrent intents, ack≠fill, timeout, network, reject, malformed response, restart recovery, SQLite uniqueness, reconcile found/partial/inconclusive, no blind retry, Phase 1A UNKNOWN block, dry-run non-executing, mainnet lock, write-session retry isolation.

Live scripts (`main.py`, `run_agent.py`, `test_connection.py`) were **not** run.

---

## Remaining risks

| Risk | Severity | Notes |
|------|----------|-------|
| Manual CLI still retry-unsafe | High (ops) | Out of Phase 1B |
| ACCEPTED not auto-promoted to FILLED | Medium | Needs richer fill polling (Phase 1C) |
| Correlation id from reason hash can collide across days if identical | Low | Prefer explicit bar-close correlation later |
| Reconcile “no match” never clears unresolved alone | Intended | May block new entries until manual/ops proof |
| Not exactly-once at exchange | — | At-most-one local submit attempt per intent |
| `set_leverage` still best-effort before entry | Low | Pre-existing |
| SQLite single-host prototype | — | Fine for research MVP; not multi-region SaaS |

---

## Manual CLI risks not addressed

- `bot/api.call_api` retries around `place_order`
- No `orderLinkId` intent ledger for manual orders
- Confirm UX still accepts `y` on mainnet
- Uncapped manual leverage

---

## Recommendations for Phase 1C

1. Confirmed/closed-bar signal gating (audit forming-candle risk).
2. Persisted daily loss halt.
3. Fill/position reconciliation loop to advance `ACCEPTED` → `FILLED` with evidence.
4. Optional operator tool to resolve stuck `RECONCILIATION_REQUIRED` intents safely.
5. Apply intent/`orderLinkId` patterns to manual CLI write path (or isolate CLI from retries).

---

## Acceptance criteria

| Criterion | Status |
|-----------|--------|
| Same intent cannot trigger multiple independent local submissions | **Pass** |
| Unknown submission result never blind-retried | **Pass** |
| Intent persists before submission | **Pass** |
| Restart recovery handles unresolved intents safely | **Pass** |
| Phase 1A position UNKNOWN still blocks | **Pass** |
| Offline tests pass | **Pass** (42) |
| No actual trading / no stage-commit-push | **Pass** |

---

*End of Phase 1B report.*
