# Phase 4D Gate B — Migration Preparation Report

**Prompt:** 54 · Prepare only · **execution not authorized**  
**Date:** 2026-11-07  

Prior Gate B0 / CONDITIONAL assessments are **not** treated as apply authorization.

---

## Phase A — Inventory

| Item | State |
| --- | --- |
| Active Alembic HEAD | `20261105_0003` |
| Proposed migration | `versions_proposed/20261107_0004_…` (not discoverable) |
| Config gates | Signal writes/sync default **false**; binding persistence **false**; `AGENT_ALLOW_LIVE` default false |
| DB target guards | `verify_dev_database_target` + Alembic `_assert_dev_migration_target` |
| Approval mechanisms | Env `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` + operator docs |
| Missing prerequisites | Live identity confirmation; backup evidence; explicit apply instruction |

Dependencies reviewed: `cloud_models`, `cloud_repository`, `cloud_sync`, `owner_binding`, `cloud_history_router`, JWT verifier, SQLite store, decision payload, import dry-run.

---

## Final readiness assessment

| ID | Area | Status |
| --- | --- | --- |
| A | Repository migration readiness | **STATIC PASS** |
| B | Target project identity | Local config STATIC PASS · remote **NOT VERIFIED** |
| C | Backup and restore readiness | **NOT VERIFIED** (blocking unqualified GO) |
| D | SQLite preservation readiness | **PASS** (inspect + fixture backup API) |
| E | Offline PostgreSQL migration compatibility | **NOT VERIFIED** — skipped (no confirmed disposable local PG; port 5432 not proven isolated; Supabase not used as testbed) |
| F | Security and ownership readiness | **STATIC PASS** (app filters mandatory; privileged URL BYPASSRLS advisory) |
| G | Dev-only DDL migration readiness | **REQUIRES APPROVAL** (blocked on backup/identity + explicit instruction) |
| H | Cloud-write activation readiness | **FAIL** / not ready — gates must stay OFF |
| I | Automatic synchronization readiness | **FAIL** / not ready — disabled |
| J | Historical import readiness | **FAIL** / not ready — dry-run only |

### Offline PostgreSQL simulation

**Skipped.** `psql`/`docker` not on PATH; TCP `127.0.0.1:5432` was observed open but **not** confirmed as a disposable non-Supabase database. No connection attempted under this prompt’s safety rules.

---

## Security / activation gates (unchanged)

| Flag | Prep expectation |
| --- | --- |
| `SIGNAL_SUPABASE_WRITES_ENABLED` | false / unset |
| `SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED` | false / unset |
| `SIGNAL_CLOUD_SYNC_ENABLED` | false / unset |
| `EXCHANGE_BINDING_PERSISTENCE_*` | false |
| `AGENT_ALLOW_LIVE` | false |
| `TESTNET_ORDER_SUBMISSION_APPROVED` | false / unset |
| `PERPETUAL_AUTO_EXECUTION_ENABLED` | false / unset |
| `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` | **false** (do not enable in prep) |

Lifespan may autoload **local** signal engine if `SIGNAL_AUTO_ENGINE_ENABLED` — that path does **not** start cloud sync or place orders.

Least-privilege recommendation (document only): future runtime DB role without BYPASSRLS; migrator role elevated only for Alembic; Data API remains SELECT-own RLS without write policies.

---

## Offline tests

See `PHASE_4D_GATE_B_OFFLINE_TEST_RESULTS.md` — **82** Python passed; **32** Vitest; `tsc` passed.

---

## Deliverables

1. `PHASE_4D_GATE_B_MIGRATION_PREPARATION.md` (this file)  
2. `PHASE_4D_GATE_B_PROJECT_IDENTITY.md`  
3. `PHASE_4D_GATE_B_SCHEMA_REVIEW.md`  
4. `PHASE_4D_GATE_B_BACKUP_CHECKLIST.md`  
5. `PHASE_4D_GATE_B_SQLITE_PRESERVATION.md`  
6. `PHASE_4D_GATE_B_OFFLINE_TEST_RESULTS.md`  
7. `PHASE_4D_GATE_B_EXECUTION_RUNBOOK.md`  
8. `PHASE_4D_GATE_B_APPROVAL_REQUEST.md`  

**Proposed migration not moved. Not applied. No cloud changes.**
