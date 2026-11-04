# Phase 2B — Final Pre-Flight (Session Pooler :5432)

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Project | CryptoNova Trading Platform |
| Mode | Read-only preflight only |
| Alembic `upgrade` / `downgrade` / `stamp` | **Not executed** |
| Bybit / trading | Not contacted |
| Secrets / full `DATABASE_URL` | Not printed |

Prior reports reviewed: `PHASE_2B_MIGRATION_READINESS_REPORT.md`, `PHASE_2B_SUPABASE_PREFLIGHT_REPORT.md` (prior NOT READY on `:6543`).

---

## Redacted database identity

| Field | Observed |
|-------|----------|
| Configured | Yes |
| Redacted URL | `postgresql+psycopg://postgres.wmirifmgaftassgrfbyl:***@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require` |
| Host | `aws-0-ap-southeast-2.pooler.supabase.com` |
| Database | `postgres` |
| Pooler username project ref | `wmirifmgaftassgrfbyl` (dev identity match) |
| Server `current_user` | `postgres` |
| Region hint | `ap-southeast-2` |
| Connectivity | **CONNECT_SUCCESS** |

Intended development Supabase project: **confirmed** via redacted pooler host + project-ref username (no password recorded).

---

## Connection mode and TLS

| Check | Result |
|-------|--------|
| Port | **5432** |
| Classification | **session_pooler** |
| Direct / Session (migrate-safe) | **Yes** |
| Transaction pooler `:6543` | No longer active |
| `sslmode` | `require` |
| TLS effective | **Yes** |
| `migrate_connection_mode_ok` | **True** |

---

## Current migration revision / catalog

| Check | Result |
|-------|--------|
| Schema `app` | **Does not exist** |
| `app.alembic_version` | Absent |
| App tables (`agent_decisions`, `system_events`, `strategy_configs`) | Absent |
| Recorded revision | `None` |
| State | **`pending_fresh`** |
| Target revision | `20261104_0001` |
| Migration required | **Yes** |
| Targets `app` only (offline audit) | **True** |

---

## Operator dashboard schema-exposure confirmation

| Item | Status |
|------|--------|
| Verifiable via this read-only SQL session | **No** |
| Status | **REQUIRES_OPERATOR_DASHBOARD_CONFIRMATION** |
| Required action | Settings → API → Exposed schemas → ensure **`app` is not listed** |

This remains a human checklist item before/at approval time; it does not block the technical READY signal for connection mode + pending migrate.

---

## Offline test results

| Check | Result |
|-------|--------|
| `uv run pytest -q` | **129 passed** |
| Remote DDL/DML | None |
| SQLite trading ledgers | Not modified by this run |

---

## Remaining before apply

1. Operator confirms Exposed schemas exclude `app`.
2. Operator sends **explicit approval** to apply `20261104_0001` on this **development** project (Session/Direct `:5432` only).
3. Only then run (not executed now):

```powershell
uv run alembic -c apps/api/alembic.ini upgrade head
```

---

## Recommendation

# READY

Technical preflight passed:

- Session pooler **`:5432`** + TLS `require`
- Development project identity matches
- Migration **`20261104_0001` pending** on a fresh catalog (no `app` schema yet)
- Offline suite green (**129 passed**)

**Do not apply** until explicit operator approval. This report does **not** authorize `alembic upgrade head`.
