# Phase 4D — Gate Summary

## Status: DESIGN + GATED CODE COMPLETE — **READ-ONLY PREFLIGHT: CONDITIONAL GO (DDL only assessment)**

See `PHASE_4D_PREFLIGHT_AUDIT.md` and `PHASE_4D_APPROVAL_CHECKLIST.md`.  
Writes/sync/import remain **NO-GO**. No cloud changes executed in preflight.

### Delivered (no cloud mutation)

| Item | Status |
|------|--------|
| Read-only audit of Alembic/RLS/SQLite/4C | Done |
| Schema plan + proposed revision `20261107_0004` | Done — **not applied** (`versions_proposed/`) |
| Dual cloud write/sync kill switches (default OFF) | Done |
| SQLAlchemy models + owner-scoped repository | Done (writes gated) |
| Local SQLite outbox (schema v3) | Done |
| Sync health API + Studio badges | Done |
| SQLite import dry-run tool | Done (refuses cloud execute) |
| Docs set | Done |

### Explicitly NOT done (needs your approval)

- [ ] Run Supabase / Alembic migrations creating signal tables  
- [ ] Enable `SIGNAL_SUPABASE_WRITES_*` / `SIGNAL_CLOUD_SYNC_ENABLED`  
- [ ] Import existing SQLite history into Supabase  
- [ ] Create Auth users / change DB roles  
- [ ] Enable exchange binding persistence (separate decision)  

### Evidence kill switches remain safe

- Binding persistence flags untouched (still false by design)  
- `AGENT_ALLOW_LIVE` / private reads unchanged  
- Wallet configuration unused by signal/cloud path  
- No Bybit orders / no private agent exchange calls  

### Startup (unchanged local path)

```powershell
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8200
cd apps\web; npm run dev
```

Dry-run import planner:

```powershell
.\.venv\Scripts\python.exe scripts\phase4d_sqlite_import_dry_run.py
```

---

## OPERATOR APPROVAL CHECKPOINT

Reply explicitly if you approve any of the following (individually):

1. **Apply DDL** — move `20261107_0004` into `alembic/versions` and run upgrade against the configured Supabase project  
2. **Enable cloud writes** — set dual `SIGNAL_SUPABASE_WRITES_*` gates (still no binding persistence)  
3. **Enable sync drain** — `SIGNAL_CLOUD_SYNC_ENABLED=true` after (1)+(2)  
4. **Import SQLite history** — run a gated importer for a specific Auth `owner_user_id`  

Until then, Supabase remains **not** the live SoT for signals; local SQLite continues to persist decisions safely.
