# Phase 4D — Migration Runbook (DO NOT EXECUTE WITHOUT GATE B)

## Prerequisites

- [ ] Target Supabase project identity verified  
- [ ] Backup readiness evidenced (see `PHASE_4D_BACKUP_RECOVERY.md`)  
- [ ] Alembic HEAD is `20261105_0003`  
- [ ] Proposed file reviewed: `apps/api/alembic/versions_proposed/20261107_0004_phase4d_signal_persistence.py`  
- [ ] Explicit operator approval for Gate B  

## Exact steps (approval required)

1. Move/copy revision from `versions_proposed/` into `alembic/versions/`.  
2. `cd apps/api && alembic upgrade 20261107_0004` using the project `DATABASE_URL`.  
3. Verify tables/indexes/RLS with read-only SQL.  
4. Do **not** enable write/sync flags in the same change window without Gates C/D.  

## Failure response

- Stop; restore from verified backup if partial apply.  
- Do not invent compensatory writes from the trading engine.  

## Rollback

`alembic downgrade 20261105_0003` drops Phase 4D tables — only if empty/acceptable data loss.
