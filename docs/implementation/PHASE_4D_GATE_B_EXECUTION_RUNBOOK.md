# Phase 4D Gate B — Future Execution Runbook

**COMMANDS DOCUMENTED ONLY — NOT EXECUTED.**

Applies only after a **separate, explicit** operator instruction naming revision `20261107_0004` and project `wmirifmgaftassgrfbyl`.

---

## Pre-execution checks

- [ ] Explicit written approval for **DDL-only** Gate B (this revision only)  
- [ ] Dashboard confirms project `wmirifmgaftassgrfbyl`  
- [ ] Backup evidence filed **or** written residual-risk acceptance  
- [ ] SQLite backup via backup API verified (`data/backups/…`)  
- [ ] Migration checksum / file review of proposed revision  
- [ ] Alembic HEAD still `20261105_0003` on target  
- [ ] Env guards for apply window: `CRYPTONOVA_DB_TARGET=development`, `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes`  
- [ ] Cloud write gates OFF: `SIGNAL_SUPABASE_WRITES_*=false`, `SIGNAL_CLOUD_SYNC_ENABLED=false`  
- [ ] Binding persistence OFF  
- [ ] `AGENT_ALLOW_LIVE=false`, `TESTNET_ORDER_SUBMISSION_APPROVED` unset/false, `PERPETUAL_AUTO_EXECUTION_ENABLED` unset/false  

---

## Execution preparation (future)

1. **Promote file (only when approved):**  
   Source: `apps/api/alembic/versions_proposed/20261107_0004_phase4d_signal_persistence.py`  
   Destination: `apps/api/alembic/versions/20261107_0004_phase4d_signal_persistence.py`  
2. Expected revision: `20261107_0004`  
3. Exact future command (from repo root):

```powershell
# DOCUMENTATION ONLY — DO NOT RUN UNDER THIS PREPARATION PROMPT
$env:CRYPTONOVA_DB_TARGET="development"
$env:CRYPTONOVA_ALLOW_DEV_MIGRATIONS="yes"
# Ensure CRYPTONOVA_DEV_PROJECT_REF and approved DATABASE_URL already point at wmirifmgaftassgrfbyl
uv run alembic -c apps/api/alembic.ini upgrade 20261107_0004
```

4. Expected schema changes: CREATE five `app.signal_*` / `app.scheduler_*` tables + indexes + RLS SELECT policies. No cloud writes of signal rows.

---

## Post-migration verification (future, sanitized)

- `alembic current` → `20261107_0004`  
- Tables exist under `app`  
- Columns / UNIQUE / FK / indexes match review  
- RLS enabled; SELECT-own policies present; no INSERT policies for `authenticated`  
- Existing tables (`agent_decisions`, `system_events`, `strategy_configs`, `exchange_account_bindings`) preserved  
- No unexpected data rows in new tables (expect empty)  

---

## Failure response

1. Stop all further activation (writes/sync/import).  
2. Capture sanitized error (no URLs/passwords).  
3. Inspect transaction / `app.alembic_version`.  
4. Do **not** blind-retry.  
5. Keep SQLite as signal/risk SoT.  
6. Prefer forward-fix; avoid downgrade if any data landed (downgrade drops tables).  

---

## Post-success restrictions

Keep disabled:

- Cloud signal writes  
- Automatic cloud sync  
- Historical SQLite import  
- Exchange binding persistence  
- All Bybit order submission / live trading  

Immediately set `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false` after the apply window.
