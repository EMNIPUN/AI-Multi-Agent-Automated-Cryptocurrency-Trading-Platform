# Phase 3B Part 1 — Worker observability

| Field | Value |
|-------|-------|
| Date | 2026-11-05 |
| Scope | Durable worker telemetry, fail-closed reads, honest command-center status |
| `PRIVATE_DATA_READS_ENABLED` | **false** (unchanged) |
| Migration `20261104_0002` | **Not applied** |
| Live SSE | **Still 403** — deferred |
| Real order HTTP | **Not added** |
| Bybit wallet route | **Unchanged** |

---

## Audit

- `AgentRunner` did not publish events. The publisher hook defaulted to a null sink.
- Observability HTTP returned labeled SAMPLE snapshots. Live snapshot without fixture mode returned 503. Authenticated SSE returned 403.
- Wallet reads stay on operator-local server credentials. There is still no per-user exchange binding.
- Execution, fill, and risk SQLite stores were not used for this ledger.

## Event producer

`AgentRunner` records telemetry only when a `TelemetryLedger` is passed. `run_agent.py` opens `OBSERVABILITY_LEDGER_PATH` (default `data/observability_ledger.sqlite`). Tests that construct a runner without a ledger are unchanged.

Emitted only after the matching step has actually happened:

| Event | When |
|-------|------|
| `agent.started` / `agent.stopped` | Process start / keyboard stop |
| `agent.heartbeat` | A tick has started. This is worker liveness, not the last signal |
| `agent.error` | Candle fetch raised |
| `market.candle_confirmed` | Confirmed-candle filter accepted bars |
| `analysis.completed` | Strategy returned EMA/RSI |
| `signal.generated` | Includes HOLD. HOLD is not a trade |
| `risk.halted` | Durable risk view is halted |
| `risk.blocked` | Position state is UNKNOWN, or `plan_trade` returned no plan |
| `risk.approved` | A trade plan object was produced |

`order.*` types are accepted by the ledger and snapshot projector, but the runner does **not** emit them. `execute()` returning true is not evidence of ACCEPTED vs FILLED, so those events wait until an explicit intent state is read.

`_observe` and `safe_record` swallow telemetry failures. A ledger error does not change the tick result.

## Store

Separate SQLite table `observation_events` (not the risk or intent database).

- `event_id` unique; duplicates are ignored
- UTC timestamps, schema version, correlation id, env scope
- Account label is the static string `operator-local` (no fingerprint)
- Payloads pass through `sanitize_public_json` (API keys redacted)
- Growth capped at 5,000 newest rows
- Cursor is the integer `seq`

## Heartbeat

Snapshot status comes from the ledger, not from the web server:

- No heartbeat row → `UNKNOWN`
- Heartbeat older than the stale window → `OFFLINE`
- Stop event at or after the last heartbeat → `OFFLINE`
- Halt at or after the last heartbeat → `HALTED`
- Fresh heartbeat → `RUNNING`, even when the last signal is HOLD

No heartbeat row is invented when the ledger is empty.

## Authorization

`GET /api/v1/observability/worker-snapshot`

- Loopback hosts only (`127.0.0.1`, `::1`, `localhost`, test client)
- **403** if an `Authorization` header is present — a Supabase user is not an owner of this operator ledger
- Unconfigured or empty ledger → `data_mode=unavailable`, `agent_status=UNKNOWN`, no SAMPLE events
- Public `GET /snapshot` is still the labeled fixture when fixture mode is on

SSE is unchanged and still denied. No token in the query string.

Set `OBSERVABILITY_LEDGER_PATH` on the API process to the same file the worker writes. Until that path is set, the dashboard worker view stays unavailable.

## UI

`/agents/live` polls `source=worker` by default and does not fall back to fixtures.

- SAMPLE is an explicit toggle (`source=sample`) and replaces the worker view; the two are not merged
- Workflow nodes stay idle when status is unavailable
- Animated list renders only events in the selected snapshot
- Notifications still request `source=sample` so they stay labeled samples
- Wallet panel is untouched

## Tests

```text
uv run pytest -q
189 passed, 1 warning

apps/web npm run typecheck
tsc --noEmit completed with no reported errors

apps/web npm run lint
No ESLint warnings or errors
(existing SWC Win32 binary warning; lint still completed)

apps/web npm run test:events
check-events.mjs: ok
```

Production build was not re-run in this pass.

## Still blocked

1. No verified user ↔ exchange-account binding, so real telemetry is not a browser user API.
2. Migration `20261104_0002` is not applied. Do not enable `PRIVATE_DATA_READS_ENABLED` for this ledger.
3. Authenticated SSE stays off.
4. Order lifecycle events are not emitted from the runner yet.
5. Candle series are not copied into the worker snapshot (indicators and timestamps only).

## Next milestone

Read explicit intent states from the existing intent store (read-only) and emit `order.intent_created` / `order.accepted` / fill events from those rows, still without placing orders. Keep the worker snapshot loopback-only until an ownership binding exists. Then consider SSE.
