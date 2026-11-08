# Phase 4D — Cloud Sync Design

## Default: DISABLED

Worker and drain no-op unless:

1. Dual write gates open  
2. `SIGNAL_CLOUD_SYNC_ENABLED=true`  
3. `SIGNAL_CLOUD_OWNER_USER_ID` is a valid UUID (verified Auth user)

## Worker behavior (`drain_outbox_once` / `CloudSyncWorker`)

- Recover stale `IN_PROGRESS` leases → `RETRY_WAIT`  
- Claim bounded batch → `IN_PROGRESS`  
- Validate payload schema; legacy summaries → `PERMANENT_FAILURE`  
- Idempotent `upsert_decision_payload`  
- Mark `SYNCED` only after cloud commit confirmation  
- Ambiguous commit → retry (never false SYNCED)  
- Exponential backoff + jitter; permanent after max attempts / classification  

## Retention

Pending/retry rows are retained until synced or permanent failure. Operators reconcile permanent failures from local `signal_history` after approval — never discard silently.
