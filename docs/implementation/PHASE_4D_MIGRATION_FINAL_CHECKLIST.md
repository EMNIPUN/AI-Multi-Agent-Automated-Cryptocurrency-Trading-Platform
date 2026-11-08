# Phase 4D Gate B0 — Migration Final Checklist (`20261107_0004`)

**File:** `apps/api/alembic/versions_proposed/20261107_0004_phase4d_signal_persistence.py`  
**Moved to active versions:** **no**  
**Upgrade/downgrade/stamp run:** **no**

## Static verification

| Check | Evidence | Result | Severity | Blocking Gate B apply? |
| --- | --- | --- | --- | --- |
| Parent revision | `down_revision=20261105_0003` | PASS | — | — |
| Active HEAD | `scripts/_static_alembic_4d_check.py` → heads `['20261105_0003']`, `down_matches_active_head=True` | PASS | — | — |
| Not discoverable yet | `discoverable_by_default_alembic=False` (intentional) | PASS | Process | Must move only after approval |
| Table conflicts | `table_name_conflicts_with_active=[]` | PASS | — | — |
| Schema | `app` + UUID / BIGINT / TIMESTAMPTZ / JSONB | PASS | — | — |
| Unique constraints | decision_id; owner+idempotent_key; signal_id+agent_id; owner+eval_key; owner+local_audit_id | PASS | — | — |
| Foreign keys | contributions/risk → `signal_history` with CASCADE / SET NULL | PASS | — | — |
| Indexes | owner/ts, symbol/tf, strategy, risk ms, eval stream, audit ms | PASS | — | — |
| RLS | ENABLE + SELECT-own TO `authenticated` only (no INSERT) | PASS | Advisory | Soft |
| ORM alignment | `cloud_models.py` UniqueConstraints match DDL names | PASS | — | — |
| ORM CHECKs | category/action CHECKs exist in DDL; not duplicated on ORM | Residual low | Docs only | No |
| Downgrade | Drops policies then tables — **destructive** if populated | FAIL if used casually | High | Do not auto-downgrade |
| Upgrade data loss | Additive CREATE only | PASS | — | — |
| Transaction behavior | Alembic default; some DDL may autocommit on Postgres | Residual | Medium | Operator aware |
| Identity guard (code) | `alembic/env.py` expects `wmirifmgaftassgrfbyl` | PASS | — | — |
| Migration allow flag | `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false` | PASS (fail-closed) | — | Blocks accidental apply |

## Safe-to-apply assessment (development schema only)

**Repository static review:** compatible with expected chain after `20261105_0003`.  

**Live empty-vs-populated remote schema:** **NOT VERIFIED** this session (no privileged remote catalog probe by design).

## Required before any apply (separate Gate B approval)

1. Operator confirms project `wmirifmgaftassgrfbyl`  
2. Backup evidence checklist completed  
3. Explicit approval text for DDL-only  
4. Move file into `alembic/versions/`  
5. Set `CRYPTONOVA_DB_TARGET=development` + `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes` for the apply window only  
6. Keep all `SIGNAL_SUPABASE_WRITES_*` / `SIGNAL_CLOUD_SYNC_ENABLED` **false**
