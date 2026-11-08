# Phase 4D — Complete Architecture (Local Implementation)

**Status:** IMPLEMENTED (local) · SUPABASE ACTIVATION REQUIRES APPROVAL  
**Strategy:** 4B.1.0 · Auto-engine: 4C.1.0 · Payload schema: 4D.1.0  
**Alembic HEAD (applied):** `20261105_0003` · Proposed: `20261107_0004` (not applied)

## Separation of concerns

| Layer | Responsibility | Authority |
| --- | --- | --- |
| A. Local SQLite | Paper risk, scheduler lock/checkpoint, durable decisions, outbox, retry metadata | Risk + lock SoT |
| B. Supabase PostgreSQL | Long-term signal/agent/risk/strategy/scheduler mirrors, future backtest/paper/journal | Mirror after confirmed sync |
| C. Repository | Owner filters, idempotent upsert, pagination, error classification | App-layer authz (RLS bypass possible) |
| D. Frontend | History, sync health, analytics tallies — no DB secrets | Browser via FastAPI |

## Safety defaults

- `SIGNAL_SUPABASE_WRITES_ENABLED=false`
- `SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED=false`
- `SIGNAL_CLOUD_SYNC_ENABLED=false`
- Exchange binding persistence unchanged / independently gated
- No Bybit order submission from signal path

## Data flow

1. Confirmed candle → SignalPipeline → CoordinatorDecision  
2. Atomic SQLite TX: signal_history + paper_risk + outbox(+checkpoint)  
3. Optional gated sync worker drains outbox → owner-scoped cloud upsert  
4. Cloud history APIs require verified JWT `sub` as owner  

Trading engine core safety decisions never depend on cloud availability.
