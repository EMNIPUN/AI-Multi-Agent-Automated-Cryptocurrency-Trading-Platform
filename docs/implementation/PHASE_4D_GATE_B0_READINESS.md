# Phase 4D — Gate B0 Readiness Verification

**Date:** 2026-11-07  
**Mode:** READ-ONLY · no cloud DDL · no migration · no write/sync enablement · no exchange orders · no git commit  

**Expected development project ref:** `wmirifmgaftassgrfbyl`

---

## Final decision

# NO-GO

**Mandatory prerequisites missing or independently unverified:**

1. **Supabase backup / PITR / restore evidence — NOT VERIFIED** (blocking)  
2. **Live remote Supabase identity — NOT VERIFIED** without a non-privileged catalog probe (operator confirmation still required)  

**Repository verification** of config consistency, proposed migration static safety, SQLite v4 preservation, security gate defaults, and local disposable backup API tests: largely **PASS**.

A future **CONDITIONAL GO** for *dev-only additive DDL* is possible only after the operator either:

- files backup evidence per `PHASE_4D_BACKUP_EVIDENCE_CHECKLIST.md`, **or**  
- explicitly accepts residual schema-recovery risk in writing for an empty/dev apply  

This Gate B0 result **does not authorize** migration execution.

Distinguish clearly:

| Layer | Outcome |
| --- | --- |
| Repository / local config verification | Mostly PASS |
| Live Supabase verification | NOT VERIFIED / incomplete |
| Gate B0 overall | **NO-GO** |

---

## 1. Target identity

| Check | Evidence | Result | Severity | Blocking | Operator action |
| --- | --- | --- | --- | --- | --- |
| Alembic expected ref | `apps/api/alembic/env.py` `_EXPECTED_DEV_PROJECT_REF=wmirifmgaftassgrfbyl` | PASS | — | — | — |
| Approved allowlist | `DEFAULT_APPROVED_DEV_PROJECT_REFS` contains only this ref | PASS | — | — | — |
| Env `CRYPTONOVA_DEV_PROJECT_REF` | `wmirifmgaftassgrfbyl` | PASS | — | — | — |
| Env `SUPABASE_URL` host | `wmirifmgaftassgrfbyl.supabase.co` (redacted) | PASS | — | — | — |
| `DATABASE_URL` derived project ref | pooler user `postgres.wmirifmgaftassgrfbyl` → ref match (no URL logged) | PASS (local parse) | — | — | Confirm dashboard project |
| Live remote metadata without BYPASSRLS role | Not performed (privileged app URL intentionally unused) | **NOT VERIFIED** | Medium | Yes for apply | Operator confirm project in dashboard |
| Migration allow flag | `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false` | PASS (fail-closed) | — | Blocks accidental apply | Set only in approved window |
| DB target classification | `CRYPTONOVA_DB_TARGET=development` | PASS | — | — | — |

**Credentials / connection strings:** not reproduced in this document.

---

## 2. Backup readiness

See `PHASE_4D_BACKUP_EVIDENCE_CHECKLIST.md`.

| Requirement | Result | Severity | Blocking |
| --- | --- | --- | --- |
| Usable backup exists | **NOT VERIFIED** | High | **YES** |
| Timestamp / retention / PITR | **NOT VERIFIED** | High | **YES** |
| Restore tested | **NOT VERIFIED** | High | **YES** |
| RPO / RTO | **NOT VERIFIED** | Medium | Soft |
| Prior Phase 3C Gate B backup | Already incomplete | High | Inherited |

---

## 3. SQLite v4 preservation

See `PHASE_4D_SQLITE_V4_BACKUP_REVIEW.md`.

| Requirement | Result | Severity | Blocking |
| --- | --- | --- | --- |
| Authoritative schema v4 | PASS (`schema_version=4`) | — | No |
| Integrity check | PASS (`ok`) | — | No |
| History / risk preserved | PASS (3 signals, 1 risk row) | — | No |
| Outbox v4 columns | PASS (`lease_until_ms` present) | — | No |
| WAL handling documented | PASS | — | No |
| Disposable backup API self-test | PASS | — | No |
| Authoritative DB mutated | PASS (false) | — | No |

---

## 4. Legacy outbox recovery

See `PHASE_4D_LEGACY_OUTBOX_RECOVERY.md`.

| Requirement | Result | Severity | Blocking Gate B DDL? |
| --- | --- | --- | --- |
| Legacy → `PERMANENT_FAILURE` path exists | PASS (code) | — | No |
| Current outbox legacy rows | PASS (0 rows) | — | No |
| History without outbox (3 vs 0) | Documented; backfill design only | Medium for sync/import | No for DDL |
| Sync enabled | PASS (disabled) | — | — |

---

## 5. Migration review

See `PHASE_4D_MIGRATION_FINAL_CHECKLIST.md`.

| Requirement | Result | Severity | Blocking |
| --- | --- | --- | --- |
| Parent = active HEAD `20261105_0003` | PASS | — | — |
| Still in `versions_proposed/` | PASS (intentional) | — | Process |
| Constraints / FKs / indexes / RLS | PASS (static) | — | — |
| ORM unique alignment | PASS | — | — |
| Destructive downgrade risk | Documented | High if misused | Soft |
| Applied / stamped | **Not executed** | — | — |
| Live schema emptiness | **NOT VERIFIED** | Medium | Soft |

---

## 6. Security verification

| Check | Evidence | Result | Severity | Blocking |
| --- | --- | --- | --- | --- |
| JWT validation | `jwt_verifier.py` require exp/sub/iss/aud | PASS (code) | — | No |
| Owner-scoped cloud APIs | `/api/v1/signals/cloud/*` + JWT `sub` | PASS (code) | — | No |
| Sync owner binding | Fail-closed without `SIGNAL_CLOUD_OWNER_USER_ID` | PASS | — | No |
| Privileged DB role | App `DATABASE_URL` can BYPASSRLS — filters mandatory | PASS with **critical advisory** | Critical advisory | Soft |
| Cloud write gates | Env unset → defaults false (`SIGNAL_SUPABASE_WRITES_*`, `SIGNAL_CLOUD_SYNC_ENABLED`) | PASS | — | No |
| Binding persistence | unset / independent gates | PASS | — | No |
| `AGENT_ALLOW_LIVE` | `false` | PASS | — | No |
| Exchange order path | Phase 6A / signals `execution_allowed=False` | PASS | — | No |
| Env modified this session | No | PASS | — | — |

---

## Deliverables produced

1. `PHASE_4D_GATE_B0_READINESS.md` (this file)  
2. `PHASE_4D_BACKUP_EVIDENCE_CHECKLIST.md`  
3. `PHASE_4D_SQLITE_V4_BACKUP_REVIEW.md`  
4. `PHASE_4D_LEGACY_OUTBOX_RECOVERY.md`  
5. `PHASE_4D_MIGRATION_FINAL_CHECKLIST.md`  

Helper (local only): `scripts/_gate_b0_sqlite_inspect.py`

---

## Required operator actions before re-assessment

1. Confirm dashboard project ref is `wmirifmgaftassgrfbyl`.  
2. Complete backup evidence checklist (or written acceptance of residual risk).  
3. Optionally create a WAL-safe local SQLite backup now.  
4. Only then request **separate** Gate B approval to apply `20261107_0004`.  

Keep write/sync/import/exchange flags **off**.
