# Phase 3B Part 2 — Order lifecycle observability

| Field | Value |
|-------|-------|
| Date | 2026-11-05 |
| Scope | Evidence-based order lifecycle projection into TelemetryLedger |
| Authoritative stores | Intent/execution SQLite — **read only** |
| Telemetry store | Separate `observation_events` ledger |
| `PRIVATE_DATA_READS_ENABLED` | **false** (unchanged) |
| Migration `20261104_0002` | **Not applied** |
| Live SSE | Still disabled |
| Real order HTTP | Not added |
| Bybit wallet | Unchanged |

---

## Audited authoritative states

From `agent/order_intent.py`:

| State | Meaning |
|-------|---------|
| `CREATED` | Local intent before submit |
| `SUBMISSION_PENDING` | Mid-flight claim — not treated as ACCEPTED |
| `ACCEPTED` | Exchange ack — **not** a fill |
| `PARTIALLY_FILLED` | Evidenced partial fill; `filled_qty` kept |
| `FILLED` | Evidenced complete fill |
| `CANCELED` | Canceled; prior `filled_qty` preserved |
| `REJECTED` | Local/exchange reject |
| `UNKNOWN` | Inconclusive — not invented as filled/rejected |
| `RECONCILIATION_REQUIRED` | Needs evidence reconcile |

Intent store: `data/order_intents.sqlite3` (WAL). Executions live in `order_executions`. Observer never writes these tables.

## Architecture

```text
IntentStore (authority)
    └─ read: list_recent_for_observation(env, account_fp)
OrderLifecycleObserver.poll(TelemetryLedger)
    └─ emit stable event_id transitions only
AgentRunner.tick → _publish_order_lifecycle()  # fail-isolated
```

New modules/methods:

- `agent/order_lifecycle_observer.py`
- `IntentStore.list_recent_for_observation`
- `OrderIntent.updated_at` projected from SQLite
- Diagnostic hardening on `GET /api/v1/observability/worker-snapshot`

## Evidence → events

| Event | Emitted when journal state is |
|-------|-------------------------------|
| `order.intent_created` | `CREATED` |
| `order.accepted` | `ACCEPTED` |
| `order.partially_filled` | `PARTIALLY_FILLED` (id includes `filled_qty`) |
| `order.filled` | `FILLED` |
| `order.canceled` | `CANCELED` |
| `order.reconciliation_required` | `RECONCILIATION_REQUIRED` or `UNKNOWN` |

Not emitted from observation alone:

- `SUBMISSION_PENDING` / `REJECTED` — no inventing ACCEPTED/FILLED; UI can still show current state via order projection when those rows are listed in the observer result path; rejected has no Part 2 event type.
- Seeing `FILLED` does **not** synthesize earlier `CREATED`/`ACCEPTED` events.

Payload fields (sanitized): `intent_id`, `client_order_id`, `symbol`, `category`, `side`, `qty`, `filled_qty`, `remaining_qty`, `state`, `dry_run`, `reduce_only`, `evidence_status`, `reconciliation_required`. No `account_fp`, secrets, or raw exchange dumps.

`occurred_at` uses authoritative `updated_at` (else `created_at`), not poll time.

## Restart / idempotency

Event IDs:

- `order.intent_created:{intent_id}`
- `order.accepted:{intent_id}`
- `order.partially_filled:{intent_id}:{filled_qty}`
- `order.filled:{intent_id}`
- `order.canceled:{intent_id}`
- `order.reconciliation_required:{intent_id}` (+ `:unknown` for UNKNOWN)

Duplicate polls and process restarts insert-or-ignore. Partial fill progress changes create a new id when `filled_qty` changes. Out-of-order: only the observed state is recorded; missing earlier stages stay missing (honest gap).

Busy/locked SQLite reads retry briefly; failure returns an observation error and does not affect trading.

## Security findings

Loopback diagnostic (`/worker-snapshot`):

1. Uses ASGI `request.client.host` (TCP peer), **not** the `Host` header.
2. Rejects any `Authorization` header — no user↔exchange binding.
3. Rejects `X-Forwarded-For` / `X-Real-IP` (untrusted proxy hop).
4. Requires `API_HOST` bind in `{127.0.0.1, ::1, localhost}`.
5. Public fixture snapshot and authenticated SSE remain as before (SSE still 403).

Wallet route untouched. No secrets in telemetry payloads (asserted in tests).

## UI

`/agents/live` order table now shows:

- State badges (ACCEPTED/PARTIAL = warning; UNKNOWN/RECONCILE = danger; FILLED = success)
- Qty requested and filled
- Evidence timestamp
- Reconcile hint for ACCEPTED / PARTIAL / UNKNOWN / RECONCILIATION_REQUIRED
- Explicit copy: risk approval ≠ placement; ACCEPTED ≠ FILLED

SAMPLE and worker views remain separated by the existing toggle.

## Real vs unavailable

| Mode | Orders |
|------|--------|
| Worker ledger with observed intents | Evidenced lifecycle rows / events |
| Empty / unconfigured ledger | `unavailable` / UNKNOWN — no SAMPLE mix |
| Explicit SAMPLE toggle | Fixture only |

## Tests

```text
uv run pytest -q
204 passed, 1 warning

apps/web npm run typecheck  → pass
apps/web npm run lint       → No ESLint warnings or errors
                              (existing SWC Win32 binary warning)
apps/web npm run test:events → check-events.mjs: ok
apps/web npm run build      → exit 0 (SWC Win32 warning; build completed)
```

## Remaining blockers for private live streaming

1. No verified user ↔ exchange account ownership binding.
2. Migration `20261104_0002` not applied; `PRIVATE_DATA_READS_ENABLED` stays false.
3. SSE still deferred.
4. `REJECTED` has no dedicated observability event type yet.
5. Candle OHLCV series still not copied into worker snapshots.

## Next milestone

Bind an authenticated operator to a single exchange account fingerprint under an explicit ownership gate, then consider owner-scoped snapshots. Until then keep worker telemetry loopback-only. Optionally emit `order.rejected` as a first-class event once the contract is extended.
