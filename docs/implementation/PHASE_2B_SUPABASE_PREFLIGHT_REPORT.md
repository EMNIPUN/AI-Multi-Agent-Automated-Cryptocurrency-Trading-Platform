# Phase 2B — Supabase Pre-Flight (Read-Only)

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Project | CryptoNova Trading Platform |
| Mode | **Read-only** connectivity + catalog inspection |
| Alembic apply | **Not run** (`upgrade` / `downgrade` / `stamp` forbidden) |
| Bybit / trading | Not contacted / not changed |
| Secrets | Not printed |

Operator attestation: previously exposed Bybit and Supabase credentials **rotated** (accepted as operator statement; not independently verified here).

---

## Development database identity (redacted)

| Field | Observed |
|-------|----------|
| Configured | Yes |
| Redacted URL | `postgresql+psycopg://postgres.wmirifmgaftassgrfbyl:***@aws-0-ap-southeast-2.pooler.supabase.com:6543/postgres?sslmode=require` |
| Host | `aws-0-ap-southeast-2.pooler.supabase.com` |
| Port | **6543** |
| Database name | `postgres` |
| DB user (login role shown by server) | `postgres` |
| Supabase-like host | Yes |
| Region hint | `ap-southeast-2` |
| Connectivity | **CONNECT_SUCCESS** |

This matches the known development Supabase pooler endpoint for project ref embedded in the pooler username (`postgres.<project-ref>`). No password or raw `DATABASE_URL` is recorded in this report.

---

## Connection type and SSL

| Check | Result |
|-------|--------|
| Pooler classification | **transaction_pooler** |
| Direct / Session on **5432** | **No** (currently 6543) |
| `sslmode` | `require` |
| TLS effective for remote | Yes |
| Suitable for Alembic DDL | **No** — use Direct or Session pooler on port **5432** |

---

## Existing schema and migration version

| Check | Result |
|-------|--------|
| Schema `app` exists | **False** |
| `app.alembic_version` | Absent |
| `app.agent_decisions` | Absent |
| `app.system_events` | Absent |
| `app.strategy_configs` | Absent |
| `alembic_version` value | `None` |
| Migration state | **`pending_fresh`** |
| Migration required | **Yes** (`20261104_0001` not applied) |

No partial/manual `app` objects were detected.

---

## Migration scope validation

Offline audit (`audit_initial_migration` + review SQL artifact):

- Targets schema **`app` only**
- Does not alter Supabase-managed `auth` / `storage` / `realtime`
- `migration_targets_app_only_audit_ok=True`

---

## Data API exposure verification

| Method | Status |
|--------|--------|
| Local/SQL definitive proof of PostgREST “Exposed schemas” | **Not available** |
| Status | **REQUIRES_OPERATOR_DASHBOARD_CONFIRMATION** |

**Operator action:** Supabase Dashboard → **Project Settings** → **API** → **Exposed schemas** → confirm **`app` is not listed**.

Optional later: after migrate, run reviewed `apps/api/sql/revoke_public_api_access.sql` (not executed in this pre-flight).

---

## Offline test results

| Check | Result |
|-------|--------|
| `uv run pytest -q` | **129 passed** |
| `.env` gitignored | Yes |
| SQLite ledgers gitignored | `data/order_intents.sqlite3`, `data/account_risk.sqlite3` (and related patterns) ignored |
| SQLite stores | Present under `data/`; **not modified** by this pre-flight |
| Trading settings | Unchanged (no edits to dry-run / allow-live controls) |

---

## Remaining blockers

1. **Switch `DATABASE_URL` to Direct or Session Pooler on port `5432`** (keep `sslmode=require`), then re-run:

   ```powershell
   Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
   uv run python scripts/supabase_preflight_readonly.py
   ```

2. **Dashboard confirmation** that Exposed schemas exclude `app`.

3. **Explicit written approval** to run `alembic upgrade head` on this **development** project (see `PHASE_2B_MIGRATION_READINESS_REPORT.md`).

4. Keep process-env free of leftover review URLs (a prior localhost `review_only` override can shadow `.env`).

---

## Recommendation

# NOT READY

**Reason:** connectivity and fresh pending migration look good, but the active URL is the **transaction pooler (`:6543`)**, which is not the approved migrate path.

After switching to **Direct or Session `:5432`**, re-run pre-flight. If that returns `RESULT=READY` and Exposed schemas are confirmed, the project can proceed to an **operator-approved** `alembic upgrade head` only.

---

## Commands used (safe)

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
uv run python scripts/supabase_preflight_readonly.py
uv run pytest -q
```

**Not run:** `alembic upgrade`, `downgrade`, `stamp`, any remote DDL/DML writes, Bybit calls, trading CLIs.
