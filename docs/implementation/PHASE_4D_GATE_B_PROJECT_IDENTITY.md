# Phase 4D Gate B — Project Identity Preparation

**Expected development ref:** `wmirifmgaftassgrfbyl`  
**Remote live probe this session:** **not performed**  
**Status:** local configuration **STATIC PASS** · remote target **NOT VERIFIED**

## Local configuration consistency (no secrets printed)

| Check | Result |
| --- | --- |
| `alembic/env.py` `_EXPECTED_DEV_PROJECT_REF` | `wmirifmgaftassgrfbyl` |
| `DEFAULT_APPROVED_DEV_PROJECT_REFS` | contains only this ref |
| `CRYPTONOVA_DEV_PROJECT_REF` (local env) | matches expected |
| `SUPABASE_URL` host pattern | `*.supabase.co` matches expected ref |
| `DATABASE_URL` project-ref parse (host/user, redacted) | matches expected (pooler user pattern) |
| `CRYPTONOVA_DB_TARGET` | `development` |
| `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` | `false` (fail-closed; do **not** set to yes in this prep) |

Matching local configuration is **not** proof the operator will apply against the intended live project.

## Migration guard behavior (code)

`scripts/verify_dev_database_target.py` + Alembic `_assert_dev_migration_target()`:

1. Requires `CRYPTONOVA_DB_TARGET=development` (production/ambiguous rejected)  
2. Requires approved `CRYPTONOVA_DEV_PROJECT_REF` in allowlist  
3. Rejects production deny-list refs  
4. Requires connection project-ref match (or explicit local disposable flag)  
5. With `require_migration_approval=True`, requires `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes`  
6. Missing vars → safe failure  

**Future approved apply window only (document, do not set now):**

```text
CRYPTONOVA_DB_TARGET=development
CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes
```

## Operator dashboard confirmation checklist

In Supabase Dashboard (read-only):

1. Open project selector → confirm ref **`wmirifmgaftassgrfbyl`**.  
2. Settings → General → copy Project ID; must match.  
3. Confirm region/host expectations match your stored pooler host pattern (do not paste passwords).  
4. Confirm this is the **development** project, not a future production project.  
5. Record confirmation date/time in the approval request.

## Classification

**TARGET IDENTITY: NOT VERIFIED** (remote) — operator confirmation required before any apply.
