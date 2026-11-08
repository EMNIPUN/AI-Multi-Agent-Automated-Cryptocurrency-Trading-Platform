# Phase 4D — Read-Only Preflight Audit

**Scope:** Inspection, offline tests, documentation only.  
**Cloud changes executed:** none.  
**Date context:** 2026-11-07 (local preflight).

## Recommendation (assessment only)

### CONDITIONAL GO

Schema-only migration may be considered for a **separately approved, development-only** Alembic apply after prerequisites below.  

**Write enablement, cloud sync, and SQLite import remain NO-GO** until sync completeness, authenticated owner APIs, and backup evidence are addressed.

This assessment is **not** authorization to migrate.

## Doc ↔ code differences

| Topic | Docs claim | Code reality | Severity |
|-------|------------|--------------|----------|
| Proposed revision location | `versions_proposed/20261107_0004` | Present; **not** in `alembic/versions` | Info (intentional) |
| Alembic discoverability | Must move before upgrade | `alembic.ini` `script_location=apps/api/alembic` → default `versions/` only — **not discoverable** until moved | Medium (process) |
| Dual write gates | OFF by default | `cloud_gates.py` + `ApiSettings` defaults false; `.env` lacks explicit keys (defaults apply) | Pass |
| Sync drain | Designed | `drain_outbox_once` **always** raises `cloud_ddl_not_applied_awaiting_operator_approval` even if gates forced | High for sync cutover; safe while gated |
| Outbox payload | Full decision sync | Pipeline enqueues **summary only** (`decision_id`, action, etc.) — insufficient to rebuild `CoordinatorDecision` | High for sync |
| ORM vs DDL | Models mirror schema | `cloud_models.py` lacks UNIQUE `(owner, idempotent_key)` / CHECK constraints present in proposed DDL | Low (DDL is SoT if applied) |
| Signal history SoT | Local until sync | Correct; API history still reads **SQLite only** | Pass / note |
| Backup readiness | Not asserted in 4D docs | Prior Phase 3C docs: backup **unverified** | Blocker for unqualified GO |

## Audit matrix

| # | Requirement | Evidence | Status | Severity | Action | Blocks migration? |
|---|-------------|----------|--------|----------|--------|-------------------|
| 1 | Project identity | `alembic/env.py` `_EXPECTED_DEV_PROJECT_REF=wmirifmgaftassgrfbyl`; identity guard on migrate | PASS (code) / remote live **NOT VERIFIED** | Medium | Confirm target before apply | Yes for apply without confirm |
| 2 | Alembic revision chain | Active HEAD `20261105_0003`; proposed `down_revision=20261105_0003` | PASS (static) | — | Move file only after approval | Process |
| 3 | Schema compatibility | New table names; no conflict with `agent_decisions` etc. | PASS (static) | — | — | No |
| 4 | JWT validation | `jwt_verifier.py` requires exp/sub/iss/aud; JWKS ES256/RS256 | PASS (code review) | — | Keep app filters | No |
| 5 | Owner isolation | Repo filters `owner_user_id`; offline cross-user test | PASS (offline) | — | Cloud list APIs must require JWT post-cutover | Conditional |
| 6 | RLS + privileges | SELECT-own for `authenticated`; privileged `DATABASE_URL` bypasses RLS | PASS with advisory | **Critical advisory** | Never claim RLS protects FastAPI role | Soft (app filters mandatory) |
| 7 | Write gates | Dual flags + sync flag default off; no startup drain | PASS | — | Keep off | No |
| 8 | Outbox idempotency | UNIQUE `event_id`; local decision persist atomic | PASS local / FAIL sync completeness | High | Complete payload + upsert path | Blocks **sync** not DDL |
| 9 | Crash recovery | SQLite WAL intents/checkpoints; outbox pending survives | PASS local | — | — | No |
| 10 | Backup readiness | Phase 3C Gate B incomplete; no restore test evidence | **NOT VERIFIED** | High | Operator snapshot/PITR + note RPO/RTO | Yes for unqualified GO |
| 11 | SQLite preservation | Import plan forbids delete; dry-run refuses execute | PASS (design) | — | Backup SQLite file before import | No for DDL |
| 12 | Cloud outage | Local persist + outbox; sync gated | PASS | — | — | No |
| 13 | Test coverage | See test section | PASS offline | — | Not production proof | No |
| 14 | Exchange isolation | Signals/automation gates; 6A submission off | PASS | — | Keep separate | No |

## Test count discrepancy (40 vs 33)

**Not a regression.** Selection difference:

| Suite | Count |
|-------|------:|
| `test_phase4a_multi_agent_signals.py` | 15 |
| `test_phase4b_signal_history.py` | 10 |
| `test_phase4c_auto_signal_engine.py` | 15 |
| **4A+4B+4C** | **40** |
| `test_phase4d_supabase_signal_persistence.py` | 8 |
| **4B+4C+4D** | **33** |

## Offline tests executed this preflight

```text
pytest tests/test_phase4a_multi_agent_signals.py \
       tests/test_phase4b_signal_history.py \
       tests/test_phase4c_auto_signal_engine.py \
       tests/test_phase4d_supabase_signal_persistence.py \
       tests/test_phase6a_automation_foundation.py -q
66 passed

npm run typecheck → pass
npm test → 32 passed
```

No order submission, no privileged exchange trading calls, no Supabase writes.

## REMOTE SUPABASE VERIFICATION: NOT PERFORMED

No suitable non-privileged read-only catalog connection was used. Privileged `DATABASE_URL` was intentionally not used for “read-only” verification (BYPASSRLS). Local inference ≠ live DB verification.

## Prerequisites for a separately approved **dev-only schema** migration

1. Explicit operator approval for DDL apply only  
2. Confirm Dev project ref `wmirifmgaftassgrfbyl`  
3. Operator-confirmed usable backup/snapshot (or written acceptance of residual risk)  
4. Copy SQLite `data/multi_agent_signals.sqlite3` backup  
5. Move `20261107_0004` into `alembic/versions/`  
6. `CRYPTONOVA_DB_TARGET=development` + `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes`  
7. Keep all `SIGNAL_SUPABASE_WRITES_*` / `SIGNAL_CLOUD_SYNC_ENABLED` **false** after DDL  

**Do not** enable writes/sync/import in the same approval unless sync payload + JWT-scoped cloud history APIs are completed and re-audited.
