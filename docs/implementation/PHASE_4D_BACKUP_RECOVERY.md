# Phase 4D — Backup & Recovery

## Evidence status

| Item | Status |
| --- | --- |
| Supabase automated backup availability | **NOT VERIFIED** (no cloud probe executed) |
| Snapshot / restore procedure evidence | **NOT VERIFIED** |
| Restore test evidence | **MISSING** → **blocks Gate B** |
| Local SQLite backup | Operator responsibility: copy `data/multi_agent_signals.sqlite3` before import/migration |

## Recommended operator checks (manual, not executed here)

1. Confirm Supabase project PITR / daily backups in dashboard.  
2. Document RPO/RTO targets for personal use.  
3. Practice restore into a disposable project before applying `20261107_0004`.  
4. Copy local SQLite to timestamped backup.  

## Rollback risk

Proposed downgrade **drops** new tables — do not auto-downgrade a populated database.
