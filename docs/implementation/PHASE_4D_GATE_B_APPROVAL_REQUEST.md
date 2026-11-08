# Phase 4D Gate B — Approval Request Package

**Status:** Prepared for operator decision — **migration not executed**  
**Scope:** Single gate, single revision  

## Exact request

Authorize **development-only** Alembic upgrade to:

| Field | Value |
| --- | --- |
| Revision | **`20261107_0004`** |
| File | `20261107_0004_phase4d_signal_persistence.py` |
| Parent | `20261105_0003` |
| Target project (expected) | **`wmirifmgaftassgrfbyl`** |
| Change type | Additive DDL in schema `app` |

### Cloud schema objects this revision would create

1. `app.signal_history`  
2. `app.signal_agent_contributions`  
3. `app.signal_risk_events`  
4. `app.scheduler_evaluation_history`  
5. `app.scheduler_audit`  

Plus associated indexes, unique/check constraints, FKs, and **RLS ENABLE + SELECT-own policies** for role `authenticated`.

### Explicitly **excluded** from this approval

- Enabling `SIGNAL_SUPABASE_WRITES_ENABLED` / `OPERATOR_APPROVED`  
- Enabling `SIGNAL_CLOUD_SYNC_ENABLED`  
- Starting the sync worker  
- Importing SQLite history into Supabase  
- Creating Supabase Auth users  
- Enabling exchange binding persistence  
- Bybit Testnet or Mainnet order submission  
- Connecting SignalPipeline to execution  
- Production deployment / Git push  

A “yes” to Gate B DDL must **not** be treated as approval for Gates C–F.

## Prerequisites the operator must confirm

1. Dashboard project identity `wmirifmgaftassgrfbyl`  
2. Backup evidence **or** written residual backup-risk acceptance  
3. SQLite backup completed via backup API  
4. Cloud write/sync/order flags remain OFF after apply  

## Suggested operator reply format

```text
APPROVE GATE B DDL ONLY
revision=20261107_0004
project=wmirifmgaftassgrfbyl
backup=VERIFIED|RESIDUAL_RISK_ACCEPTED
cloud_writes=remain_disabled
sync=remain_disabled
import=not_authorized
orders=not_authorized
```
