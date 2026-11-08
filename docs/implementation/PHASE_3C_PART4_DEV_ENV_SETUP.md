# Phase 3C Part 4 — Isolated Supabase Development Environment Setup

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Production project | **Must remain untouched** |
| Development migrations in this prep | **Not executed** |

---

## Why a separate project

### Operator clarification (2026-11-06)

The existing Supabase project **`wmirifmgaftassgrfbyl`** was created for **development** and has **never** been designated as a production deployment. **Do not create another Supabase project.**

Read-only probe confirmed:

- Host: `aws-0-ap-southeast-2.pooler.supabase.com` (session pooler `:5432`)
- Alembic: **`20261104_0001`**
- Tables empty (`agent_decisions` / `system_events` / `strategy_configs` = 0 rows)
- Pending: `0002`, `0003`

No separate production database is currently designated. Future production projects must be added to `CRYPTONOVA_PROD_PROJECT_REFS`.

Production **Gate B** (backup / Data API / prod readiness) remains a separate concern and stays **INCOMPLETE** until those evidences exist — even though this project is classified development.

---

## Current status (this workspace)

| Item | Result |
|------|--------|
| Development project ref | **`wmirifmgaftassgrfbyl`** (verified) |
| Separate second project | **Not required / not created** |
| Migration approval package | `PHASE_3C_PART4_DEV_RECLASS_MIGRATION_APPROVAL.md` |

---

## Configure local env (after project exists)

### API

```bash
cp apps/api/.env.development.example apps/api/.env.development
# Edit placeholders only in the gitignored file
```

Required identity vars:

```text
CRYPTONOVA_DB_TARGET=development
CRYPTONOVA_DEV_PROJECT_REF=<dev-ref>
DEV_DATABASE_URL=<dev session-pooler or direct URL>
CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false
PRIVATE_DATA_READS_ENABLED=false
OBSERVABILITY_LIVE_STREAM_ENABLED=false
```

Also set `DATABASE_URL` to the **same development** database for FastAPI/Alembic runtime (never production). Prefer keeping `DEV_DATABASE_URL` as the guard’s source of truth.

### Web

```bash
cp apps/web/.env.development.example apps/web/.env.development.local
```

Use the **development** `NEXT_PUBLIC_SUPABASE_URL` + anon key only.
Keep `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false`.

### Auth

- Configure redirect URLs for `http://localhost:3000/**` on the **development** project.  
- Keep JWT verification (`AUTH_JWT_MODE=jwks`) enabled — do not disable auth.  
- Do not mix production access tokens with the development API.

### Exchange / worker

- No production Bybit keys.  
- Prefer testnet/demo placeholders if any.  
- No auto enrollment of production bindings.  
- `EXCHANGE_ACCOUNT_BINDING_ID` only after a **dev** attested binding exists.

---

## Verify identity before any write

```bash
# From repo root — never prints passwords
uv run python scripts/verify_dev_database_target.py
# Optional SELECT-only probe:
uv run python scripts/verify_dev_database_target.py --connect
# Before approved migrations:
uv run python scripts/verify_dev_database_target.py --require-migration-approval --connect
```

Reject cases (by design): missing target, production classification, production project ref, hostname/ref mismatch, missing approval flag.

---

## Isolation rules

| Do | Don't |
|----|-------|
| Separate project ref + keys | Reuse production service_role / DATABASE_URL |
| Dev Auth users only | Copy production users/data |
| Fail-closed private-read flags | Enable private SSE / live trading |
| Guard script before migrate | Run `alembic upgrade` against ambiguous URLs |

---

## Relationship to production Gate B

Successful development setup **does not** mark production Gate B PASS.
Production still needs backup/PITR evidence, Data API exposure confirmation, and separate Gate C approval.
