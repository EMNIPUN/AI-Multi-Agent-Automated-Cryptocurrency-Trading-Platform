# Current Status Audit — 2026-11-04

| Field | Value |
|-------|-------|
| Scope | Whole-repo phase status + safety posture (no secret values) |
| Exchange | Bybit V5 only (CLI / `agent`) |
| Managed DB | Supabase PostgreSQL (dev connectivity verified earlier) |
| Execution SoT | Local SQLite intents / executions / risk |

---

## Executive summary

Phase **0 → 1E** trading safety core is implemented. Phase **2A/2B** FastAPI + Supabase foundation is implemented. Live **DB ping succeeded** earlier today; **Alembic migrations are not yet applied** to Supabase (pending explicit operator apply).

**Blocker found during this audit:** empty `API_CORS_ORIGINS=` in `.env` caused pydantic-settings JSON parse failure on API import. **Fixed** by marking `cors_origins` with `NoDecode` and re-validating.

**Security finding:** Real credentials previously existed in local `.env` and were visible in an earlier chat turn. **Rotate Bybit API key/secret and Supabase DB password**; keep `.env` gitignored; never paste `.env` into chat.

---

## Phase completion matrix

| Phase | Topic | Status |
|-------|-------|--------|
| 0 | Repo hygiene / ignore rules | Done |
| Monorepo scaffold | `apps/`, `packages/`, `docs/` | Done |
| 1A | Fail-closed positions | Done |
| 1B | Durable order intents / idempotency | Done |
| 1C | Persistent risk / halt | Done |
| 1D | Confirmed candles / signal ledger | Done |
| 1E | Evidence-based fill reconciliation | Done |
| 2A | Read-only FastAPI + Alembic models | Done |
| 2B | Supabase URL/SSL, migration bootstrap, privacy plan | Done (code); migrate not applied |
| 2C+ | Auth, RLS, read APIs, sync projections | **Not started** |
| Web / Worker | Next.js, worker runtime | Scaffold only |

---

## Runtime posture (labels only — no secrets)

| Control | Expected / observed |
|---------|---------------------|
| `AGENT_DRY_RUN` | Should stay `true` until deliberate live test |
| `AGENT_ALLOW_LIVE` | Should stay `false` unless intentional mainnet live |
| `BYBIT_TESTNET` / `BYBIT_DEMO` | Check local `.env`; mainnet without dry-run is high risk |
| API bind | `127.0.0.1` default |
| CORS | Empty = disabled (no `*`) |
| Trading HTTP routes | Not registered |
| Private data HTTP | Stub → 401 |
| SQLite SoT | Untouched by Phase 2 schema |
| `.env` / `data/*.sqlite3` | Gitignored |

---

## FastAPI / Supabase

| Item | Status |
|------|--------|
| `apps.api.main:app` | Present; startup prints redacted DB status |
| Endpoints | `GET /health`, `GET /api/v1/system/status` |
| `DATABASE_URL` | Supported (psycopg3, SSL for remote) |
| Live ping | Succeeded earlier (transaction pooler `:6543`) |
| Schema `app` migration `20261104_0001` | Prepared; **not confirmed applied** on remote |
| Data API exposure of `app` | Must remain unexposed; revoke SQL is manual |
| Auto remote migrate | Disabled by design |

---

## Test posture

| Checkpoint | Result |
|------------|--------|
| Phase 2B report baseline | 128 passed |
| Mid-audit (empty CORS env bug) | Failures/errors until fix |
| Post-fix (this audit) | Re-run recorded below in “Verification” |

---

## Risks / open items

1. **Credential rotation** after `.env` exposure in chat.
2. **Mainnet flags** in local env — confirm dry-run before any agent live path.
3. **Transaction pooler (6543)** — OK for ping; prefer Session `5432` / Direct for Alembic.
4. **Migrations not applied** — tables may not exist on Supabase until `upgrade head`.
5. **No Auth/RLS** — do not expose `app` via PostgREST; no private HTTP data APIs yet.
6. **Dual ledger risk** — do not treat Postgres as execution authority until a designed sync phase.
7. Manual protective flatten / cancel-all still operator-owned (Phase 1E).

---

## Recommended next actions

1. Rotate exposed credentials; update local `.env` only.
2. Restart API and confirm `[db] status=connected CONNECT_SUCCESS`.
3. When ready: `alembic upgrade head --sql` review → approve → `upgrade head`.
4. Apply `apps/api/sql/revoke_public_api_access.sql` + confirm `app` not in Exposed schemas.
5. Start Phase 2C: authentication + RLS before any private read APIs.

---

## Verification

| Check | Result |
|-------|--------|
| Empty `API_CORS_ORIGINS` settings load | Fixed (`NoDecode`) |
| API import with local `.env` | `api_import=ok` |
| DB configured (local) | `True` (pooler/ssl labels only) |
| Offline pytest | **129 passed** (post CORS + test isolation fixes) |
