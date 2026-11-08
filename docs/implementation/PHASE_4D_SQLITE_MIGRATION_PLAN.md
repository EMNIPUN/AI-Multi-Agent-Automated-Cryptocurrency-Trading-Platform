# Phase 4D — SQLite → Supabase Migration Plan

## Tool

```powershell
.\.venv\Scripts\python.exe scripts\phase4d_sqlite_import_dry_run.py
.\.venv\Scripts\python.exe scripts\phase4d_sqlite_import_dry_run.py --db data\multi_agent_signals.sqlite3
```

Default mode: **dry-run**. `--execute-cloud-import` is **refused**.

## Planning checklist

1. Backup: copy `data/multi_agent_signals.sqlite3` to a timestamped file.
2. Run dry-run; confirm row counts and idempotency_check.pass.
3. Do **not** delete or replace the SQLite file.
4. Wait for operator approval of DDL `20261107_0004`.
5. Apply Alembic only after approval.
6. Set dual write gates + sync gate only after Auth principal mapping is decided.
7. Import with upsert on `decision_id` / `(owner_user_id, idempotent_key)` — no silent overwrite of divergent payloads (fail or skip).
8. Reconcile counts: SQLite vs Supabase per owner.
9. Resume: re-run upserts safely; already-imported keys no-op.
10. Keep local outbox / risk / lock intact.

## Mapping

| SQLite | Supabase |
|--------|----------|
| `signal_history` | `app.signal_history` + contributions + risk_events |
| `evaluation_checkpoints` | `app.scheduler_evaluation_history` |
| `scheduler_audit` | `app.scheduler_audit` |
| `paper_risk_state` | **Not imported as SoT** — local remains authoritative |
| `scheduler_lock` | **Never imported** |
| `cloud_sync_outbox` | Local only |

## Owner assignment

Import must stamp `owner_user_id` from a verified operator Auth user (JWT `sub`). CLI `--owner-user-id` is for planning notes only until a gated importer is approved.
