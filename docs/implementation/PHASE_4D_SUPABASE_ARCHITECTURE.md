# Phase 4D — Supabase Architecture (design + gated code)

## Decision

Supabase PostgreSQL (`app` schema) is the **intended central persistent store** for CryptoNova trading-system records.

Local SQLite remains a **required safety buffer** for:
- Single-process scheduler lock
- Authoritative paper-risk halt/cooldown state (until a later promotion)
- Durable outbox for cloud sync
- Offline recovery

## Current state (as of this gate)

| Layer | Status |
|-------|--------|
| Existing Alembic HEAD | `20261105_0003` |
| Existing tables | `agent_decisions`, `system_events`, `strategy_configs`, `exchange_account_bindings` |
| Signal history today | **SQLite only** (`data/multi_agent_signals.sqlite3`) |
| Proposed signal DDL | `alembic/versions_proposed/20261107_0004_*.py` — **NOT APPLIED** |
| Cloud writes | **OFF** (`SIGNAL_SUPABASE_WRITES_*`, `SIGNAL_CLOUD_SYNC_ENABLED`) |
| Binding persistence | **Unchanged / OFF** |

## Authority model

| Concern | Authoritative store | Cloud role |
|---------|---------------------|------------|
| Paper risk halt / seen keys | Local SQLite `paper_risk_state` | Mirror risk events only |
| Scheduler single-writer lock | Local SQLite `scheduler_lock` | Not replaced by Postgres |
| Signal decisions | Local SQLite first; outbox | Idempotent upsert after gates |
| Eval checkpoints | Local first | Mirror `scheduler_evaluation_history` |
| Exchange credentials | Env / binding refs (separate) | Never in signal tables |

**Conflict policy:** Local risk + lock win for process safety. Cloud upserts are idempotent on `decision_id` / `(owner, eval_key)`. Never double-count risk from cloud retries. Unsynced outbox ≠ cloud success.

## Request path

```
Browser → Next.js same-origin proxy → FastAPI (JWT verify)
  → owner_user_id = JWT sub only
  → repository WHERE owner_user_id = :principal
  → DATABASE_URL (privileged today — RLS not sufficient alone)
```

## Kill switches (independent of bindings)

```
SIGNAL_SUPABASE_WRITES_ENABLED=false
SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED=false
SIGNAL_CLOUD_SYNC_ENABLED=false
```

Both write flags must be true before any Supabase signal INSERT. Sync requires those plus `SIGNAL_CLOUD_SYNC_ENABLED`.

## Operator approval required before

1. Moving proposed revision into `alembic/versions/` and running `alembic upgrade`
2. Enabling write/sync env flags
3. Running a live SQLite→Supabase import (dry-run tool refuses `--execute-cloud-import`)
4. Creating Auth users or changing DB roles/GRANTS
