# Phase 4D — Atomic Persistence

## Single transaction boundary

`SignalHistoryStore.persist_decision_and_risk` uses `BEGIN IMMEDIATE` and commits:

1. Signal decision insert (idempotent on unique keys)  
2. Paper-risk state update  
3. Cloud outbox enqueue with full `4D.1.0` payload  
4. Optional evaluation checkpoint  

Any failure rolls back the entire unit. Injected failure hooks (`_test_fail_after`) cover each stage offline.

## Pipeline / auto-engine wiring

- `SignalPipeline.evaluate(..., checkpoint=...)` persists atomically with full outbox payload.  
- Auto-engine passes `CheckpointWrite` into evaluate so successful evaluations do not advance checkpoint without durable decision+outbox.  
- Duplicate candle / decision keys do not double-enqueue outbox (`event_id = signal:{decision_id}`).

## Guarantees

- WAL mode + RLock preserved  
- No silent omit of outbox after decision persist  
- Cloud success is never inferred from local outbox insert alone  
