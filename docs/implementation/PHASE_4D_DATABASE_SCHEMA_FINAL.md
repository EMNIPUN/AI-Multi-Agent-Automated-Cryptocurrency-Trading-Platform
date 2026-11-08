# Phase 4D — Database Schema Final

## Local SQLite (`data/multi_agent_signals.sqlite3`) — schema v4

- `signal_history` — durable decisions  
- `paper_risk_state` — risk SoT  
- `evaluation_checkpoints` / `scheduler_lock` / `scheduler_audit`  
- `cloud_sync_outbox` — statuses: `PENDING`, `IN_PROGRESS`, `RETRY_WAIT`, `SYNCED`, `PERMANENT_FAILURE` + `lease_until_ms`

## Proposed Supabase (`app` schema) — revision `20261107_0004`

Tables (NOT APPLIED):

- `app.signal_history` — UNIQUE(`decision_id`), UNIQUE(`owner_user_id`,`idempotent_key`)  
- `app.signal_agent_contributions` — UNIQUE(`signal_id`,`agent_id`)  
- `app.signal_risk_events`  
- `app.scheduler_evaluation_history` — UNIQUE(`owner_user_id`,`eval_key`)  
- `app.scheduler_audit` — UNIQUE(`owner_user_id`,`local_audit_id`)  

ORM models in `apps/api/app/signals/cloud_models.py` aligned with DDL unique constraints.  
RLS SELECT policies for `authenticated` are defense-in-depth; FastAPI owner filters remain mandatory.
