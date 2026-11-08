# Phase 4D Gate 62 — Execution Report

| Field | Value |
| --- | --- |
| Status | **MIGRATION_VERIFIED** |
| Date (UTC) | 2026-11-07 |
| Project | `wmirifmgaftassgrfbyl` (`ap-southeast-2`) |
| Revision applied | `20261108_0005` |
| Prior revision | `20261107_0004` |
| Migration SHA-256 | `9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a` |
| Executor | `scripts/_gate_62_execute_0005.py` |

---

## 1. Authorization (operator message)

Operator explicitly authorized Gate 62 for Supabase development project `wmirifmgaftassgrfbyl` only; Alembic revision `20261108_0005`; required SHA-256 `9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a`; accepted unverified managed backup / PITR risk and skip of backup preparation; authorized only reviewed security roles, grants, RLS policies, and Alembic metadata update; stop on mismatch; **did not** authorize Gate 63, cloud writes, sync, historical imports, exchange orders, or deployment.

---

## 2. Pre-apply checks

| Check | Result |
| --- | --- |
| Proposed file SHA-256 | **MATCH** |
| Active `versions/` before promote | absent (clean) |
| Project ref | `wmirifmgaftassgrfbyl` |
| Region host | `aws-0-ap-southeast-2.pooler.supabase.com` |
| Server | PostgreSQL **17.11** |
| Remote Alembic | `20261107_0004` |
| `cryptonova_*` roles | **0** |
| Phase 4D row counts | **0 / 0 / 0 / 0 / 0** |
| Cloud write / sync / order / binding flags | **OFF / unset** |
| `AGENT_ALLOW_LIVE` | `false` |
| `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` (env file) | `false` (session window only during apply) |
| Backup / PITR | **NOT VERIFIED** — operator accepted |

---

## 3. Apply

1. Promoted `versions_proposed/20261108_0005_option_a_least_privilege.py` → `alembic/versions/` (checksum re-verified).
2. Session flags: `CRYPTONOVA_DB_TARGET=development`, `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes` (process only).
3. `alembic upgrade 20261108_0005` — exit **0**.
4. Identity guard logged: `classification=development project_ref=wmirifmgaftassgrfbyl`.
5. Session migration allow flag restored to **false**.

---

## 4. Post-apply verification

| Check | Result |
| --- | --- |
| Alembic | `20261108_0005` |
| Active file SHA-256 | **MATCH** |
| `cryptonova_api_runtime` | NOLOGIN, NOBYPASSRLS, NOSUPERUSER, **INHERIT** |
| `cryptonova_migrator` | NOLOGIN, NOBYPASSRLS, NOSUPERUSER, **INHERIT** |
| `cryptonova_role_count` | **2** |
| Runtime policies | SELECT/INSERT/UPDATE on signal tables; SELECT on scheduler + catalog |
| Authenticated SELECT policies | **intact** |
| Table owners | still `postgres` |
| Phase 4D row counts | still **0** |
| Runtime grants sample (`signal_history`) | SELECT, INSERT, UPDATE |
| Migrator `CREATE ON SCHEMA app` | **true** |
| FastAPI / runtime credential | **unchanged** (still privileged `postgres` path) |
| Gate 63 | **not performed** |
| Cloud writes / sync / orders | **not enabled** |

Offline regression: `tests/test_option_a_least_privilege_security.py` + `tests/test_phase4d_gate_c1_security.py` → **21 passed, 1 skipped**.

Note: `_gate_c1_readonly_catalog.py` still compares Alembic to `20261107_0004`, so `remote_alembic_match False` after Gate 62 is expected; live value is correctly `20261108_0005`.

---

## 5. Explicit non-actions

- No Gate 63 FastAPI credential cutover / LOGIN wrapper creation
- No `RUNTIME_DB_IDENTITY_ENABLED`
- No cloud writes, sync worker, historical import
- No exchange Testnet/Mainnet orders
- No git push / deploy
- No FORCE RLS / REASSIGN OWNED

---

## 6. Residuals / next gate

1. FastAPI still connects as BYPASSRLS-capable `postgres` until **Gate 63**.
2. Managed backup / PITR remains **NOT VERIFIED**.
3. Alembic downgrade does not DROP roles.
4. Live RLS enforcement under `cryptonova_api_runtime` requires Gate 63 + LOGIN member.

**STOP.** Await separate explicit approval for Gate 63 (or later gates).
