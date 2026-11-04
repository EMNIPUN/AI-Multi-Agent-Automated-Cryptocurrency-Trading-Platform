# Worker observability publisher plan (Phase 3A)

## Goals
- Emit append-only observability events from `AgentRunner.tick()` without changing order behavior.
- Heartbeat + staleness for Command Center.
- Reconnect: client loads snapshot, then applies `cursor` catch-up.

## Non-goals
- Do not write into SQLite intent/risk/fill SoT for UI.
- Do not call Bybit from the publisher.
- Do not enable live SSE until ownership migration + `PRIVATE_DATA_READS_ENABLED`.

## Adapter
- Protocol: `ObservabilityPublisher.publish(event) -> bool` (idempotent by `event_id`).
- Default: `NullObservabilityPublisher`.
- Buffer: `ObservabilityEventBuffer` (in-memory) for local/dev; later Redis/NATS/Postgres `app.system_events` with sanitization.

## Suggested emission points (future PR)
| Runner moment | Event type |
|---------------|------------|
| Start of tick | `agent.heartbeat` |
| Confirmed candles accepted | `market.candle_confirmed` |
| Strategy evaluate returns | `analysis.completed` + `signal.generated` |
| Risk plan None / blocked | `risk.blocked` |
| Risk plan ok | `risk.approved` |
| Intent created | `order.intent_created` |
| Exchange ack / fills (existing reconcile) | `order.accepted` / `partially_filled` / `filled` |
| Halt | `agent.halted` |
| Unexpected errors | `agent.error` |

## Reconnect
1. `GET /api/v1/observability/snapshot`
2. SSE or poll with `cursor=<last_event_id>`
3. Dedup by `event_id` on the client

## Auth
- Browser uses same-origin Next.js proxy; Authorization header only (never JWT in query string).
