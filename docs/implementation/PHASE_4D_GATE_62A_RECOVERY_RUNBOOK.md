# Phase 4D Gate 62A — Recovery Runbook (NON-EXECUTED)

```
╔════════════════════════════════════════════════╗
║  NON-EXECUTED PROCEDURE                        ║
║  Do not run against Supabase unless separately ║
║  authorized after a failed Gate 62 attempt.    ║
╚════════════════════════════════════════════════╝
```

**Baseline inventory:** `PHASE_4D_GATE_62A_SECURITY_INVENTORY_SNAPSHOT.json`  
**Target project:** `wmirifmgaftassgrfbyl` only  
**Never paste passwords or full DATABASE_URL into this file.**

---

## 1. Purpose

Restore **security configuration** (roles / grants / policies / Alembic awareness) after a failed or unwanted Gate 62 apply — when managed backup restore is unavailable or not authorized.

This is **not** a full database restore.

---

## 2. Preconditions

- [ ] Confirm project ref still `wmirifmgaftassgrfbyl`
- [ ] Capture fresh RO inventory and compare to Gate 62A snapshot
- [ ] FastAPI still on privileged connection (Gate 63 not done)
- [ ] Cloud write / sync / order flags OFF
- [ ] Explicit recovery authorization recorded (separate from Gate 62 apply)

---

## 3. Detection (read-only)

```powershell
uv run python scripts/_gate_c1_readonly_catalog.py
uv run python scripts/_gate_61_readonly_role_probe.py
uv run python scripts/_option_a_readonly_rls_inventory.py
uv run python scripts/_gate_62a_readonly_security_inventory.py
```

Compare: Alembic version, `cryptonova_role_count`, policies named `*_runtime_*`, Phase 4D counts (expect 0).

---

## 4. Recovery paths

### Path A — Migration failed before Alembic stamp

Expected: few or no cryptonova objects; version still `20261107_0004`.

1. List `cryptonova_%` roles and `*_runtime_*` policies.
2. If policies exist without desire to keep them:

```sql
-- ILLUSTRATIVE — requires separate approval; filter to known policy names only
-- DROP POLICY IF EXISTS signal_history_runtime_select_own ON app.signal_history;
-- (repeat for known runtime policies from migration)
```

3. REVOKE grants from `cryptonova_api_runtime` / `cryptonova_migrator` if present.
4. DROP ROLE only after REVOKE and membership audit — LOGIN wrappers first if any.
5. Re-run RO inventory; confirm version `20261107_0004`.

### Path B — Migration stamped `20261108_0005` but unwanted

1. Prefer approved `alembic downgrade 20261107_0004` under migration allow-window **only** if separately authorized (downgrade does **not** DROP ROLE).
2. Manually REVOKE/DROP POLICY as in Path A.
3. Decide whether to DROP ROLE (manual; dependency check).
4. Confirm Alembic metadata and inventory.

### Path C — Managed backup restore (if later verified)

1. Only if dashboard shows a usable backup/PITR and operator authorizes restore.
2. Restore to a **non-production** verification path first if available.
3. Never combine with live order or cloud-write enablement.
4. Re-verify Alembic and row counts after restore.

### Path D — Schema-only `pg_dump` (optional local archive)

```powershell
# NON-EXECUTED EXAMPLE — do not run without approval
# Uses schema-only; still may contain object definitions; store securely offline
# & "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" --schema-only --no-owner --no-privileges ...
```

Limitations: incomplete for global roles; do not restore dump blindly to Supabase.

---

## 5. Application continuity

| Layer | Action |
| --- | --- |
| FastAPI | Keep existing `DATABASE_URL` (postgres) until Gate 63 |
| SQLite SoT | Unaffected; Gate B backup file may exist under `data/backups/` |
| Cloud writes | Remain OFF |
| Orders | Remain OFF |

---

## 6. Stop conditions during recovery

- Wrong project
- Unexpected Phase 4D row growth
- Policies/grants outside known Option A set
- Any urge to “fix” by enabling cloud writes or orders

---

## 7. Evidence to keep

- Pre- and post-recovery inventory JSON (sanitized)
- Approval quote for recovery
- List of DROP POLICY / REVOKE statements actually run (if any)
- Confirmation flags remain OFF

---

## 8. Attestation

This runbook was authored without executing recovery SQL, `pg_dump`, restore, or Gate 62 migration against Supabase.
