# Phase 1E — Evidence-Based Fill Reconciliation (Bybit V5)

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Exchange | **Bybit V5 only** (open order / order history / execution list via existing pybit session) |
| Explicitly excluded | TradingView, Apify, live trading CLIs, auto cancel-all / flatten |
| Constraints | Offline pytest only; no Bybit network; dry-run / `AGENT_ALLOW_LIVE` defaults unchanged; no commit/push |
| Related | Phase 1A / 1B / 1C / 1D reports |

---

## Root cause (pre-1E)

Phase 1B persisted order intents and could mark `ACCEPTED` from place-order acknowledgement, but reconciliation was thin:

1. **Ack ≠ fill** was stated, yet there was no durable execution ledger; fill qty came only from a single order row snapshot.
2. **Duplicate / multi-fill** executions were not deduplicated by exchange `execId`.
3. **Empty lookups** correctly avoided “never submitted,” but **ACCEPTED / PARTIAL** intents were not always re-reconciled after restart.
4. **PartiallyFilledCanceled** was mapped to `PARTIALLY_FILLED`, blurring cancel-after-partial vs still-working partials.
5. No schema migration path for new fill metadata; no transactional apply of execution evidence.
6. Out-of-order exchange echoes could theoretically fight terminal states without an explicit merge policy.

**Policy:** treat open-order, order-history, and execution-history rows as *evidence*; promote `FILLED` only with sufficient order-status (or equivalent) evidence; never treat place-order acceptance or empty search results as fill / non-submission proof.

---

## Implementation summary

```text
tick / restart
  → mark mid-flight intents RECONCILIATION_REQUIRED (1B)
  → list_needs_reconcile (UNRESOLVED ∪ ACCEPTED ∪ PARTIALLY_FILLED)
  → paginated get_open_orders / get_order_history / get_executions (read-only)
  → parse + dedupe executions by (env_scope, account_fp, execId)
  → aggregate Decimal qty / notional / fees
  → merge_reconcile_state (no terminal regression)
  → apply_reconcile_update (BEGIN IMMEDIATE; INSERT OR IGNORE execs; UPDATE intent)
  → blocking exposure: UNRESOLVED ∪ PARTIALLY_FILLED (fail closed)
```

Reconciliation **never** calls `place_order`, amend, or cancel.

---

## Files changed

| File | Role |
|------|------|
| `agent/order_intent.py` | `NEEDS_RECONCILE_STATES`, `BLOCKING_EXPOSURE_STATES`, fill metadata fields, `merge_reconcile_state` |
| `agent/intent_store.py` | Schema v2 migration, `order_executions` table, `apply_reconcile_update`, list helpers, terminal-safe `transition` |
| `agent/reconcile.py` | Paginated evidence fetch, aggregation, conflict / inconclusive handling |
| `agent/executor.py` | Reconcile ACCEPTED/PARTIAL; block on PARTIAL; surface store errors |
| `agent/runner.py` | Restart note for ACCEPTED/PARTIAL; catch reconcile store errors (no Phase 1C reset) |
| `tests/test_fill_reconciliation.py` | Phase 1E offline coverage (cases 1–22 + extras) |
| `docs/implementation/PHASE_1E_FILL_RECONCILIATION_REPORT.md` | This report |

---

## State transition design

| Evidence | Resulting state | Notes |
|----------|-----------------|-------|
| Order `New` / `Created` / … | `ACCEPTED` | Not a fill |
| `PartiallyFilled` | `PARTIALLY_FILLED` | Open residual risk; blocks new exposure |
| `Filled` + qty evidence | `FILLED` | Terminal |
| `PartiallyFilledCanceled` | `CANCELED` | **Keeps** `filled_qty` |
| `Cancelled` / `Canceled` | `CANCELED` | May have `filled_qty` > 0 |
| `Rejected` | `REJECTED` | Zero fills expected |
| Executions only (no order row) | `PARTIALLY_FILLED` | Proven activity; **not** auto-`FILLED` |
| Empty complete lookups | `RECONCILIATION_REQUIRED` | Inconclusive — not “never submitted” |
| Timeouts / API / malformed / incomplete pages | `UNKNOWN` | Fail closed |
| Qty conflict (exec sum > order qty) | `UNKNOWN` + conflict | Fail closed |
| Terminal + late ACCEPTED echo | unchanged | `merge_reconcile_state` / transition soft no-op |

Self-transitions remain allowed for metadata refresh. Invalid regressions raise or are coerced to the current terminal state.

---

## Exchange evidence sources

| Source | Bybit V5 | Use |
|--------|----------|-----|
| Open orders | `GET /v5/order/realtime` (`get_open_orders`) | Working orders by `orderLinkId` |
| Order history | `GET /v5/order/history` (`get_order_history`) | Terminal / recent by `orderLinkId` |
| Executions | `GET /v5/execution/list` (`get_executions`) | Fills by `orderLinkId` / `orderId` |

Pagination: `limit=50`, follow `nextPageCursor` up to 20 pages; sticky cursor / max pages → incomplete → inconclusive.

WebSocket private `order` / `execution` streams are **documented as future evidence channels** but not required for Phase 1E REST reconcile.

Spot vs linear: quantities, prices, and fees are stored as **exact decimal strings** (no float). Aggregation uses `Decimal`; category is recorded on execution rows. Semantics are not assumed identical between markets.

---

## Execution deduplication and quantity aggregation

- Primary key: `(env_scope, account_fp, exec_id)` on `order_executions`.
- `INSERT OR IGNORE` + in-memory dedupe before aggregate.
- Filled qty = sum of unique `execQty`; average price = Σ(qty×price)/Σ(qty); `cum_fee` = sum of `execFee` when parseable.
- When both order `cumExecQty` and exec sum exist, store the **larger** valid amount (delayed history may lag).
- Hard conflict if summed fills exceed order `qty` → `UNKNOWN`, new exposure blocked via unresolved state.

**Not claimed:** exactly-once exchange execution. Local ledger is at-least-once idempotent on `execId`.

---

## SQLite schema and migration

- `schema_meta.version = 2`
- New columns on `order_intents` (ALTER ADD, non-destructive): `remaining_qty`, `avg_exec_price`, `cum_fee`, `evidence_status`
- New table `order_executions` (FK to `order_intents`)
- Existing rows preserved; missing optional columns default to `''`

---

## Restart recovery

1. `SUBMISSION_PENDING` / `UNKNOWN` → `RECONCILIATION_REQUIRED` (Phase 1B; no blind resubmit).
2. `ACCEPTED` / `PARTIALLY_FILLED` left intact; included in `list_needs_reconcile`.
3. Prior `order_executions` reloaded and merged with fresh API pages.
4. Phase 1C `HALTED` / `RECOVERY_REQUIRED` are **never** cleared by reconcile.

---

## Protective operations (explicit gaps)

| Capability | Status |
|------------|--------|
| Read-only reconcile | Implemented |
| Auto cancel-all / close-all / flatten | **Not** implemented (by design) |
| Amend / cancel from reconcile | **Forbidden** |
| Manual CLI protective close | Still operator-owned; unresolved / partial / open positions can leave residual risk until manually managed |
| Mainnet live lock / dry-run default | Unchanged |

**Residual risk:** an `ACCEPTED` or exchange-open order may exist while the agent only blocks new exposure for `UNRESOLVED` and `PARTIALLY_FILLED`. Operators must inspect Bybit open orders / positions after incidents. Empty history after a timeout remains inconclusive forever until evidence appears — the agent will not invent a cancel.

---

## Test results

```text
.\.venv\Scripts\pytest.exe -q
104 passed
```

Phase 1E file covers: accepted without fills; single fill; multi partial; duplicate exec; out-of-order terminal; partial then cancel; reject zero fills; history-only match; execs without order row; inconclusive empty; timeout/API errors; malformed responses; pagination; restart ACCEPTED/unresolved; SQLite conflict/rollback; spot vs linear decimals; Phase 1A UNKNOWN block; Phase 1B no blind retry; Phase 1C durable halt; Phase 1D import smoke; dry-run defaults; schema migration; PARTIAL exposure block; store-error surface.

No live Bybit calls; `main.py` / `run_agent.py` / `test_connection.py` not run.

---

## Remaining risks

1. REST history delay / 7-day execution window defaults — old intents may stay inconclusive.
2. `ACCEPTED` alone does not block new exposure (same as 1B); only unresolved + partial do — open working orders need operator awareness.
3. Executions without order row never auto-promote to `FILLED` (conservative gap).
4. No websocket continuity; process downtime can miss ephemeral open-order snapshots (history/exec still used).
5. Fee currency mixtures are summed as numeric strings without FX normalization.
6. Manual protective flatten still required for incident response.

---

## Readiness for Phase 2 (FastAPI + Supabase)

| Prerequisite | Phase 1E status |
|--------------|-----------------|
| Idempotent intents | Ready (1B) |
| Evidence-based fills | Ready (local SQLite) |
| Durable risk halt | Ready (1C) |
| Confirmed candles / signal dedupe | Ready (1D) |
| Supabase mirror of intents/executions | **Not started** — migrate schema carefully; keep env/account scope keys |
| API control plane cancel/flatten | **Not started** — must stay explicit operator actions with audit |
| Multi-tenant exchange credentials | **Not started** |

Phase 2 can treat `order_intents` + `order_executions` as the local source of truth to sync, but must retain fail-closed semantics and must not enable live trading by default.
