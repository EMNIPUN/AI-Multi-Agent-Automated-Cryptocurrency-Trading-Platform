# Phase 4D — Sync Reliability Review

## Authority model (confirmed in code)

| Concern | Authoritative store |
|---------|---------------------|
| Paper risk halt / seen keys | Local SQLite `paper_risk_state` |
| Scheduler lock | Local SQLite `scheduler_lock` |
| Signal decisions (today) | Local SQLite `signal_history` |
| Cloud rows | Mirror only after successful sync (gates off → none) |

**Ambiguity during migration:** Until sync is complete and product cutover is declared, treat **SQLite as SoT for signal history**. Do not teach the UI that local rows are “cloud-confirmed.”

## Outbox (schema v3)

- Table: `cloud_sync_outbox`  
- Enqueue after local `persist_decision_and_risk` (`pipeline.py`)  
- UNIQUE `event_id` → duplicate enqueue returns false  
- Statuses: `pending` / `failed` / `synced`  
- Bounded drain limit; exponential backoff constants in `cloud_sync.py`

## Gaps (block sync enablement)

1. **Incomplete payload** — outbox stores summary fields, not full decision JSON required by `SqlAlchemySignalCloudRepository.upsert_decision`.  
2. **Drain stub** — even with gates true, drain raises `cloud_ddl_not_applied_awaiting_operator_approval`.  
3. **No scheduled worker** — good for safety now; must be explicit when enabling.  
4. **Owner mapping** — drain requires `owner_user_id` argument; no Auth-bound production caller yet.  
5. **Backlog** — failed retries can accumulate; no max-age discard policy documented in code.

## Network / crash behavior

- Local persist succeeds independent of Supabase → cloud outage does not block signals.  
- Unsynced outbox ≠ cloud success (`sync_health` semantics).  
- Crash after local persist before enqueue: possible missing outbox row (enqueue is best-effort after persist). **Severity: Medium** for eventual sync completeness — consider transactional local outbox with decision insert in a later hardening pass.

## Duplicate prevention

- Local: `decision_id` / `idempotent_key` UNIQUE  
- Cloud DDL: same + `(owner_user_id, idempotent_key)`  
- Offline repo test: idempotent upsert when gates bypassed for unit test only
