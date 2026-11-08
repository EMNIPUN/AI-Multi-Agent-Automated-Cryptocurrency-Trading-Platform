# Phase 4D Option A — Security Test Evidence

| Field | Value |
| --- | --- |
| Date | 2026-11-07 |
| Remote mutations | None |
| Disposable Postgres | **NOT AVAILABLE** (Docker not installed) |

---

## 1. Offline test results

### Option A suite — `tests/test_option_a_least_privilege_security.py`

| Area | Result |
| --- | --- |
| Identity disabled by default | PASS |
| Malformed / email owner UUID rejected | PASS |
| attach without GUC does not touch session | PASS |
| attach with GUC uses bound params | PASS |
| Missing identity fail-closed | PASS |
| Owner mismatch PermissionError | PASS |
| Pool checkout/release no leak | PASS |
| Concurrent request isolation | PASS |
| Cloud write gates fail-closed | PASS |
| Disposable Postgres RLS E2E | **SKIPPED / NOT RUN** |

### Focused security batch (earlier in Prompt 59)

115 passed, 1 skipped.

### Full Python suite

```text
475 passed, 1 skipped, 1 warning
```

Skipped: disposable Postgres RLS integration (`test_postgres_rls_integration_not_run_without_docker`).

### Frontend

- Vitest: **32 passed**
- `npx tsc --noEmit`: **exit 0**

---

## 2. RLS isolation matrix

| Scenario | Offline / mocks | Live Supabase | Disposable PG |
| --- | --- | --- | --- |
| A reads A | PASS (app filters / prior C1) | NOT VERIFIED under runtime role | NOT RUN |
| A cannot read B | PASS (mocks) | NOT VERIFIED | NOT RUN |
| A cannot insert as B | PASS (app assert helpers) | NOT VERIFIED | NOT RUN |
| Runtime NOBYPASSRLS | Documented intent | NOT VERIFIED (still postgres) | NOT RUN |
| Runtime non-owner | Documented intent | Tables owned by postgres today | NOT RUN |

**Do not claim remote least-privilege enforcement PASS.**

---

## 3. Session identity tests

| Check | Result |
| --- | --- |
| Identity only when attached | PASS |
| Cleared on release | PASS |
| No pool reuse leak | PASS |
| Concurrent isolation | PASS |
| Real SET LOCAL against Postgres | NOT RUN (no disposable PG; flag OFF) |

---

## 4. Regression / safety

| Check | Result |
| --- | --- |
| Phase 4D / C1 / auth / 6A / 3C included in full suite | PASS (475) |
| Cloud writes OFF | PASS (env inventory) |
| Sync OFF | PASS |
| Exchange orders OFF | PASS |

---

## 5. Unverified items

1. Real PostgreSQL RLS under `cryptonova_api_runtime`.
2. Live JWKS → GUC → `auth.uid()` end-to-end.
3. Role creation feasibility on this Supabase plan.
4. Sequence privilege needs after dry-run.

---

## 6. Later disposable Postgres setup (when Docker available)

```powershell
docker run --name cn-pg-opt-a -e POSTGRES_PASSWORD=localtest -p 55432:5432 -d postgres:16
# Create DB, apply 0001–0004 SQL or alembic against localhost only
# Create cryptonova_api_runtime, apply proposed policies
# Point test DATABASE_URL at localhost:55432 — never Supabase
# Run pytest -m postgres_rls (to be added when containerized)
docker rm -f cn-pg-opt-a
```

Validate host is loopback before any DDL in fixtures.
