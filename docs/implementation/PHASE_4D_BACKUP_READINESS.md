# Phase 4D — Backup Readiness

## Status: NOT VERIFIED

No evidence in this preflight of:

- Current usable Supabase backup / PITR snapshot  
- Restore procedure executed successfully  
- Restore test results  
- Documented RPO / RTO for this project  

Prior project documentation (`PHASE_3C_PART4_GATE_B_DATABASE_PREFLIGHT_REPORT.md` and related) already marked backup/PITR as **unverified / Gate B incomplete**.

## SQLite preservation (design PASS)

- Import dry-run: `scripts/phase4d_sqlite_import_dry_run.py` — refuses `--execute-cloud-import`  
- Plan requires copying `data/multi_agent_signals.sqlite3` before any future import  
- Migration must not delete SQLite files  

## Rollback strategy (schema)

- Alembic downgrade of `20261107_0004` **drops** new tables (data loss if populated)  
- Prefer forward-fix + retain SQLite SoT over casual downgrade after writes begin  

## Required before unqualified migration GO

Operator must either:

1. Confirm a usable Supabase backup/snapshot and record date/method, **or**  
2. Explicitly accept residual schema-recovery risk for a empty/dev-only apply  

A backup that has not been restore-tested must **not** be described as a verified recovery capability.
