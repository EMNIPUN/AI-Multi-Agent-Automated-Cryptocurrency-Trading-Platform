# Phase 2D — Ownership Isolation & Protected Catalog Reads

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Project | CryptoNova |
| Scope | `owner_user_id`, RLS defense-in-depth, owner-scoped FastAPI GETs |
| Private reads flag | **`PRIVATE_DATA_READS_ENABLED=false` (unchanged; not auto-enabled)** |
| Trading HTTP | Still disabled |
| Remote DDL/DML | **Not applied** — offline review only |
| Offline suite | See verification below |

---

## Ownership model and threat assumptions

### Model
- **`owner_user_id` (UUID, nullable)** on `app.agent_decisions`, `app.system_events`, `app.strategy_configs`.
- Logical link: **Supabase Auth user id** = verified JWT claim **`sub`** = `AuthenticatedPrincipal.user_id`.
- **`NULL owner_user_id`**: legacy / unowned. Ordinary users never see these rows (`WHERE owner_user_id = :principal` excludes NULL).
- **`env_scope` / `account_fp` are not ownership proofs** and are not trusted for authorization.
- Strategy names are unique **per owner** (`UNIQUE (owner_user_id, name) WHERE owner_user_id IS NOT NULL`), not globally.

### Future relationships (documented, not implemented)
- **Organizations / teams**: membership tables mapping `user_id` → `org_id`; resources may gain `org_id` with role-based grants.
- **Exchange accounts**: `exchange_accounts.owner_user_id` (or `org_id`) separate from trading SQLite SoT; API must never treat raw exchange account ids as public identifiers.

### Threat assumptions
| Threat | Control |
|--------|---------|
| Stolen anon/service_role JWT | Rejected by verifier (`non_user_token`) |
| Client-supplied `X-User-Id` | Ignored; identity only from verified JWT |
| Cross-tenant SELECT via API | Mandatory `owner_user_id = principal` filter |
| Unowned row access | NULL never matches equality filter |
| Secret leakage in JSON columns | `sanitize_public_json` + omit `account_fp` from responses |
| Sensitive system events | Blocked event_type denylist + sanitization |
| RLS bypass by postgres/table owner | Expected; **application filter is primary** |
| Pooled connection GUC bleed | FastAPI does **not** `SET ROLE` / `request.jwt.*` GUCs |
| Flag flipped without migration | Fail closed: `503 ownership_schema_unavailable` / `database_not_configured` |
| Tests alone prove production isolation | **Do not assume** — operator must review SQL + role grants |

### RLS vs application authorization
- **Application authorization (primary):** FastAPI always filters by verified `principal.user_id`.
- **RLS (defense in depth):** `ENABLE ROW LEVEL SECURITY` + `SELECT` policies for role `authenticated` using `auth.uid()`.
- **Not** `FORCE ROW LEVEL SECURITY` in this revision (avoids surprising table-owner lockouts without operator review).
- Schema `app` must remain **outside** Supabase Data API Exposed schemas; no broad `GRANT` to `anon`/`authenticated` in this revision.

---

## Files changed

### Created
| Path | Role |
|------|------|
| `apps/api/alembic/versions/20261104_0002_ownership_rls.py` | Ownership columns, indexes, RLS |
| `apps/api/sql/review/20261104_0002_ownership_rls.sql` | Offline operator review SQL |
| `apps/api/sql/runtime_role_recommendations.sql` | Least-privilege runtime role notes |
| `apps/api/app/sanitize.py` | Public JSON sanitization |
| `apps/api/app/catalog_service.py` | Owner-scoped queries + fail-closed errors |
| `tests/test_ownership_phase2d.py` | Offline isolation / sanitization / RLS review tests |
| `docs/implementation/PHASE_2D_OWNERSHIP_ISOLATION_REPORT.md` | This report |

### Updated
| Path | Change |
|------|--------|
| `apps/api/app/models.py` | `owner_user_id` + indexes; per-owner strategy uniqueness |
| `apps/api/app/ownership.py` | Docs + `assert_owner_matches` |
| `apps/api/app/routers/catalog.py` | Real owner-filtered GET handlers |
| `apps/api/app/schemas.py` | Explicit list/item response models (no `account_fp`) |
| `apps/api/app/deps.py` | Session isolation notes |
| `apps/api/app/config.py` | Version `0.2.3-phase2d` |
| `apps/api/app/migration_audit.py` | Chain-aware audit + `audit_ownership_migration` |
| `apps/api/sql/ownership_rls_plan.sql` | Points at 0002 implementation |
| `apps/api/sql/review/README.md` | Documents 0002 artifact |
| `tests/test_auth_phase2c.py` | Flag-on without DB → 503 fail closed |
| `tests/test_supabase_phase2b.py` | Ownership migration audit |

SQLite order/risk/fill stores and Bybit credentials: **unchanged**.

---

## Migration revision and SQL artifact

| Item | Value |
|------|-------|
| Revision | `20261104_0002` |
| Revises | `20261104_0001` |
| Upgrade | Additive columns/indexes + RLS enable/policies; non-destructive |
| Downgrade | Defined; **do not execute automatically** |
| Review SQL | `apps/api/sql/review/20261104_0002_ownership_rls.sql` |

**Existing rows:** `owner_user_id` remains `NULL` — no invented owners. API queries cannot return them to ordinary users.

---

## RLS design and grants

```text
ALTER TABLE app.<table> ENABLE ROW LEVEL SECURITY;
CREATE POLICY <table>_select_own ON app.<table>
  FOR SELECT TO authenticated
  USING (owner_user_id IS NOT NULL AND owner_user_id = auth.uid());
```

- Policies created only if role `authenticated` exists (Supabase).
- **No** schema `USAGE` grants to `anon`/`authenticated` in this revision.
- Recommendations for a future SELECT-only API role: `apps/api/sql/runtime_role_recommendations.sql`.

---

## FastAPI authorization and query filtering

1. Bearer JWT → `get_current_principal` (fail closed).
2. `PRIVATE_DATA_READS_ENABLED` gate → else `403 ownership_schema_required`.
3. Pagination bounds (`limit` 1–100, `offset` ≥ 0).
4. Per-request SQLAlchemy session **after** gate (no cross-request GUCs).
5. Queries: `WHERE owner_user_id = :uuid(sub)` + stable `ORDER BY created_at DESC, id DESC`.
6. Responses: Pydantic schemas; JSON sanitized; `account_fp` omitted; blocked system event types excluded.
7. DB/schema failures → `503` (`database_not_configured` / `ownership_schema_unavailable` / `catalog_query_failed`).

Endpoints:

| Method | Path |
|--------|------|
| GET | `/api/v1/agents/decisions` |
| GET | `/api/v1/system/events` |
| GET | `/api/v1/strategies` |

No mutation or trading HTTP routes added.

---

## Offline test results

```text
uv run pytest -q
164 passed, 1 warning
```

Coverage includes: owned reads, unauthenticated 401, cross-user isolation, unowned inaccessibility, pagination/ordering, query/schema fail-closed, JWT/JWKS regressions (2C), JSON sanitization, RLS/migration review, pool isolation assumptions, `PRIVATE_DATA_READS_ENABLED=false` safety, Phase 1A–1E regressions.

---

## Remaining blockers

1. **Operator must approve and apply** `20261104_0002` (and confirm `0001` state) before enabling private reads.
2. Confirm Dashboard **Exposed schemas** still exclude `app`; apply revoke script only if needed (manual).
3. Prefer a **non-BYPASSRLS** runtime DB role for FastAPI (see recommendations SQL) — today connections may be owner/postgres and bypass RLS.
4. Backfill / assign `owner_user_id` for new writes only when product rules are clear — do not invent owners for legacy rows.
5. Keep **`PRIVATE_DATA_READS_ENABLED=false`** until isolation is operator-reviewed in the target environment.
6. Offline tests **do not** prove production isolation.

---

## Explicit operator approval procedure

1. Review `apps/api/sql/review/20261104_0002_ownership_rls.sql` and Alembic source `20261104_0002_ownership_rls.py`.
2. Confirm backup / point-in-time recovery for the Supabase project.
3. Apply **only** via Alembic online upgrade against Session pooler / Direct URL (operator-run), e.g. `alembic -c apps/api/alembic.ini upgrade 20261104_0002`.
4. Verify columns + RLS: `\d+ app.agent_decisions`, `pg_policies`.
5. Re-run offline suite; optionally smoke `GET /api/v1/me` with a real user JWT (still with flag **false**).
6. Only then consider setting `PRIVATE_DATA_READS_ENABLED=true` in server env (manual; not committed as default).
7. **Do not** auto-run downgrade; **do not** expose `app` on Data API.

---

## Readiness for Next.js dashboard

| Ready | Not ready |
|-------|-----------|
| Auth contract (`/api/v1/me`) | Do not enable private catalog reads in prod yet |
| Catalog GET shapes + pagination | Need approved migration + flag flip |
| Sanitized payloads suitable for UI | Need Supabase Auth client in Next.js (Phase 3) |
| CORS `Authorization` already allowed | Never put service_role / DB URL in `NEXT_PUBLIC_*` |

**Verdict:** Phase 2D **code + offline review artifacts complete**. Production private catalog reads remain **blocked by default** until operator approval, migration apply, and explicit flag enablement.

---

## Success checklist

| Criterion | Status |
|-----------|--------|
| Ownership-aware read API implemented | Pass (behind flag) |
| Cross-user reads blocked in tests | Pass |
| RLS + migration reviewed offline | Pass (not remotely applied) |
| Unowned rows inaccessible | Pass |
| Phase 1 / 2C controls preserved | Pass |
| `PRIVATE_DATA_READS_ENABLED` still false by default | Pass |
| No remote schema changes by this phase | Pass |
| Offline pytest suite | Pass (see results above) |
