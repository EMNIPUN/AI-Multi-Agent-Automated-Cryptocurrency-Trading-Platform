# Phase 4D — Migration Review (Static)

**Source:** `apps/api/alembic/versions_proposed/20261107_0004_phase4d_signal_persistence.py`  
**Active HEAD:** `20261105_0003`  
**Proposed:** `revision=20261107_0004`, `down_revision=20261105_0003`  

Static check command:

```powershell
.\.venv\Scripts\python.exe scripts\_static_alembic_4d_check.py
```

Result (this preflight): `down_matches_active_head=True`, `discoverable_by_default_alembic=False`, no table name conflicts.

## Compatibility

| Check | Result |
|-------|--------|
| Chain continuity | PASS — parents active HEAD |
| Discoverable by Alembic now | **FAIL (intentional)** — lives under `versions_proposed/` |
| Naming conflicts | PASS — new `signal_*` / `scheduler_*` tables |
| FK order | PASS — contributions/risk FK → `signal_history` created first |
| Types | PASS — UUID, BIGINT, TIMESTAMPTZ, JSONB |
| Constraints | PASS — UNIQUE decision_id; UNIQUE (owner, idempotent_key); category/action checks |
| RLS | ENABLE + SELECT-own TO `authenticated` only (no INSERT policies) |
| Upgrade ordering | Single revision after `0003` |
| Downgrade | Drops policies then tables — **destructive** if data present |
| Data-loss on upgrade | Additive CREATE — low for empty new tables |
| Transaction boundaries | Alembic default; DDL may auto-commit on Postgres depending on ops |

## Risks

1. Applying without moving file → Alembic will not see revision.  
2. Downgrade after production data → irreversible drop.  
3. Privileged migrator role ≠ runtime least-privilege (expected).  
4. No INSERT RLS for `authenticated` — correct for Data API lockdown; FastAPI must use app role + filters later.

## Not run

`alembic upgrade`, `downgrade`, `stamp`, `revision` — **not executed**.
