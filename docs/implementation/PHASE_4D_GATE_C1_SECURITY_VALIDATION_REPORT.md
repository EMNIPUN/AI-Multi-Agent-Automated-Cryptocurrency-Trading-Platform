# Phase 4D Gate C1 — Security & Cloud Signal Persistence Validation

| Field | Value |
| --- | --- |
| Gate | **C1 only** (read-only cloud + local/mocked validation) |
| Date (local) | 2026-11-07 |
| Project | CryptoNova — `wmirifmgaftassgrfbyl` |
| Decision | **CONDITIONAL PASS** |
| Cloud writes / sync / import / orders during C1 | **None** |

---

## A. Executive summary

Gate C1 validates that Phase 4D cloud signal persistence is **correctly designed and fail-closed** before any real Supabase signal writes.

**Verified remotely:** project identity, Alembic `20261107_0004`, five empty `app` tables, RLS + SELECT-own policies, migration checksum match, runtime role `postgres` with `rolbypassrls=true`.

**Verified locally / with mocks:** dual write gates, owner-scoped repository isolation, payload `4D.1.0` execution invariants, SQLite durability under gated cloud outage, FastAPI cloud-history auth rejection, CloudSyncWorker **not** started by lifespan, full offline pytest **465 passed**, Vitest **32 passed**, `tsc --noEmit` **0**.

**Not verified:** live Supabase Auth JWT against real JWKS for cloud history E2E; RLS enforcement under a non-privileged DB role (role bypasses RLS).

**Residual critical risk (documented, not remoted-fixed):** FastAPI connects as privileged `postgres` (`BYPASSRLS`). Application-layer `owner_user_id` filters are therefore mandatory; RLS alone is insufficient for the current runtime role.

Gate C1 does **not** authorize Gate C2, cloud writes, sync workers, historical import, or exchange orders.

---

## B. Repository component map

| Component | Source | Entry | Dependencies | Safety gates | Tests |
| --- | --- | --- | --- | --- | --- |
| FastAPI app / lifespan | `apps/api/app/factory.py` | `create_app` → lifespan | auto engine opt-in, market hub | Does **not** start `CloudSyncWorker` | factory + API suites |
| SignalPipeline | `agent/multi_agent/pipeline.py` | `evaluate` | agents, risk, optional store | `execution_allowed=False` | 4A/4B/4D |
| Decision payload | `agent/multi_agent/decision_payload.py` | `build/validate_decision_sync_payload` | `CoordinatorDecision` | `4D.1.0`, not-an-order | C1 + 4D |
| SQLite SoT | `agent/multi_agent/signal_history_store.py` | atomic TX + outbox | WAL SQLite v4 | Local authority | 4B/4D/C1 |
| Cloud gates | `apps/api/app/signals/cloud_gates.py` | `get_signal_cloud_gates` | env flags | Dual write + sync | C1 matrix |
| Owner binding | `apps/api/app/signals/owner_binding.py` | `resolve_sync_owner_binding` / JWT sub | env UUID / principal | Fail-closed unset owner | C1 |
| Cloud repository | `apps/api/app/signals/cloud_repository.py` | `upsert_*` / `list_*` | SQLAlchemy, gates | Gates + owner filter | C1 + 4D |
| Cloud sync | `apps/api/app/signals/cloud_sync.py` | `drain_outbox_once` / `CloudSyncWorker` | store, repo, gates | Sync requires dual write + sync flag + owner | C1 + 4D |
| Cloud history API | `apps/api/app/signals/cloud_history_router.py` | `/api/v1/signals/cloud/*` | JWT, private-reads gate | Auth + owner from JWT sub | C1 |
| JWT verifier | `apps/api/app/auth/jwt_verifier.py` | JWKS / HS256 / static map | PyJWT, JWKS | Fail-closed | `test_auth_phase2c` |
| Alembic 0004 | `apps/api/alembic/versions/20261107_0004_…` | upgrade (already applied Gate B) | Postgres | **Not re-run in C1** | migration audit |
| ORM models | `apps/api/app/signals/cloud_models.py` | Base mappers | SQLAlchemy | Schema mirror only | 4D/C1 |
| Agent Studio | `apps/web/.../SignalsPanel.tsx` | local history + sync status badges | same-origin proxies | Shows writes/sync OFF | Vitest + TS |
| Migration auditor | `apps/api/app/migration_audit.py` | offline model↔SQL | revisions dir | No DB | phase2/3/C1 fix |

### Accidental write-path review

| Path | Can write cloud? | Evidence |
| --- | --- | --- |
| FastAPI lifespan | No | Starts auto-engine only; no sync worker |
| Scheduler / SignalPipeline | Local SQLite only | Outbox enqueue; drain gated |
| Dashboard / cloud history GET | Read paths | Writes gated in repository |
| `CloudSyncWorker.start` | Only if sync_allowed | Raises if gated; not auto-started |
| Direct repo with `require_gates=True` | Denied when flags OFF | C1 test |

---

## C. Effective configuration and safety gates

Read from `.env` keys (values not secrets; unset treated as false by gate helpers):

| Flag | Effective | Required for writes/sync |
| --- | --- | --- |
| `SIGNAL_SUPABASE_WRITES_ENABLED` | unset → OFF | Yes |
| `SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED` | unset → OFF | Yes |
| `SIGNAL_CLOUD_SYNC_ENABLED` | unset → OFF | Yes (sync) |
| `SIGNAL_CLOUD_OWNER_USER_ID` | unset | Yes (sync drain) |
| `EXCHANGE_BINDING_PERSISTENCE_*` | unset → OFF | N/A (unchanged) |
| `AGENT_ALLOW_LIVE` | `false` | Must stay false |
| `TESTNET_ORDER_SUBMISSION_APPROVED` | unset | Must stay false |
| `PERPETUAL_AUTO_EXECUTION_ENABLED` | unset | Must stay false |
| `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` | `false` | Must stay false for routine ops |
| `PRIVATE_DATA_READS_ENABLED` | `false` | Blocks private cloud history |

`cloud_writes_allowed = writes ∧ operator_approved`  
`sync_allowed = cloud_writes_allowed ∧ sync_enabled`

---

## D. Remote database identity and revision

| Check | Result | Class |
| --- | --- | --- |
| Project ref | `wmirifmgaftassgrfbyl` | **VERIFIED REMOTELY** |
| Host region | `aws-0-ap-southeast-2.pooler.supabase.com` | **VERIFIED REMOTELY** |
| Alembic version | `20261107_0004` | **VERIFIED REMOTELY** |
| Migration SHA-256 | `1ea22dc805ff5bb235fec970cec1dd9b120c0daab573b210256d50856c722145` | **VERIFIED LOCALLY** (file) |
| Session user | `postgres` | **VERIFIED REMOTELY** |
| `rolsuper` | false | **VERIFIED REMOTELY** |
| `rolbypassrls` | **true** | **VERIFIED REMOTELY** |
| Unauthorized DML during C1 | None (SELECT/catalog only) | **VERIFIED** |

Inspection tool: `scripts/_gate_c1_readonly_catalog.py` (read-only transaction / SELECT only).

---

## E. Schema and ORM compatibility matrix

All five tables exist under schema `app`, row count **0**, RLS **enabled** (not FORCE), SELECT-own policy present, grants currently only to `postgres`.

| Table | Exists | PK / uniques | RLS policy | ORM (`cloud_models`) | Drift |
| --- | --- | --- | --- | --- | --- |
| `signal_history` | Yes | pkey; `uq_decision_id`; `uq_owner_idempotent`; action/category checks | `signal_history_select_own` (SELECT) | `SignalHistoryRow` | None material |
| `signal_agent_contributions` | Yes | pkey; `uq_signal_agent`; FK → history | SELECT-own | `SignalAgentContributionRow` | None material |
| `signal_risk_events` | Yes | pkey; FK → history | SELECT-own | `SignalRiskEventRow` | None material |
| `scheduler_evaluation_history` | Yes | pkey; `uq_owner_key`; category check | SELECT-own | `SchedulerEvaluationHistoryRow` | None material |
| `scheduler_audit` | Yes | pkey; `uq_owner_local` | SELECT-own | `SchedulerAuditRow` | None material |

Column types (UUID, timestamptz, jsonb, bigint, varchar) match migration + ORM expectations. Repository queries and API schemas use the same owner-scoped decision/idempotency fields.

**No DDL changes performed in C1.**

---

## F. JWT authentication findings

Implementation: `apps/api/app/auth/jwt_verifier.py`

| Control | Status | Class |
| --- | --- | --- |
| Signature verification | JWKS ES256/RS256 allowlist; HS256 legacy separate | **VERIFIED LOCALLY** (unit) |
| Issuer / audience / exp / nbf / iat | Required in JWKS path | **VERIFIED LOCALLY** |
| Malformed / missing token | Reject | **VERIFIED WITH MOCKS** (API) |
| Invalid signature / mapping | Reject | **VERIFIED WITH MOCKS** |
| Role allowlist | `authenticated` only; reject anon/service_role | **VERIFIED LOCALLY** |
| Owner identity source | JWT `sub` via `assert_principal_matches_bound_owner` | **VERIFIED LOCALLY** |
| Client-supplied owner override | Not accepted on cloud history routes | **VERIFIED LOCALLY** (code + mocks) |
| Live JWKS E2E with real Auth session | Not executed (no Auth user creation) | **NOT VERIFIED** |
| Cross-project token rejection live | Relies on issuer/audience config | **NOT VERIFIED** live |

Fail-closed: JWKS/network/config errors raise `AuthConfigError` / `AuthError`.

---

## G. Owner isolation test results

| Scenario | Result | Class |
| --- | --- | --- |
| User A reads A history | Pass (mock SQLite-backed ORM session) | **VERIFIED WITH MOCKS** |
| User A cannot read B | Pass | **VERIFIED WITH MOCKS** |
| Nested contributions / risk leak | Pass (empty for foreign owner) | **VERIFIED WITH MOCKS** |
| Missing / invalid auth → 401 | Pass | **VERIFIED WITH MOCKS** |
| Auth OK + private reads OFF → 403 | Pass | **VERIFIED WITH MOCKS** |
| Direct decision_id lookup owner filter | Pass | **VERIFIED WITH MOCKS** |
| Live RLS as `authenticated` role | Not run | **NOT VERIFIED** |

---

## H. RLS and BYPASSRLS analysis

**Evidence:** `rolbypassrls=True` for session role `postgres`.

Implications:

1. PostgreSQL RLS policies on Phase 4D tables **do not constrain** the current FastAPI connection.
2. Isolation depends on **application-layer** `owner_user_id` predicates in `SqlAlchemySignalCloudRepository` and JWT-derived owner on APIs.
3. A coding error that omits the owner filter would be a cross-tenant data leak under the current role.
4. SELECT-own policies remain valuable for future least-privilege / PostgREST paths, but are **not sufficient today**.

Least-privilege remediation is **design-only** in Gate C1 (section O). No GRANT/REVOKE/role creation performed.

---

## I. Signal payload validation

Contract version: **`4D.1.0`** (`PAYLOAD_SCHEMA_VERSION`).

Validated components (from actual builders/validators): decision id, symbol/category/interval, strategy/config, coordinator action/scores, contributions, risk JSON, levels/market/indicators, idempotency/correlation, source metadata, timestamps.

Execution safety invariants (enforced):

- `execution_allowed=false` (type + validator reject `true`)
- `not_an_order=true`

Offline C1 test `test_payload_contract_and_execution_invariants` **PASS**. Signals remain non-executable; Phase 6A stays separate/mocked.

---

## J. SQLite integrity results

Authoritative DB: `data/multi_agent_signals.sqlite3` (read-only open during catalog).

| Check | Result |
| --- | --- |
| `PRAGMA integrity_check` | `ok` |
| `schema_version` | `4` |
| `signal_history` | **4** (baseline audit had 3; local evaluations may have added rows — not cloud) |
| `paper_risk_state` | 1 |
| `cloud_sync_outbox` | 0 pending at inspection time |
| `evaluation_checkpoints` | 0 |
| Backup present | `data/backups/multi_agent_signals_20261107_202853.sqlite3` |

Write-oriented tests used **disposable** temp SQLite only. Cloud unavailability / gates OFF do not block local persist (`test_sqlite_survives_gated_cloud_outage`).

---

## K. Cloud write-gate test matrix

| Writes | Operator | Sync | `cloud_writes_allowed` | `sync_allowed` | Evidence |
| --- | --- | --- | --- | --- | --- |
| OFF | OFF | OFF | Deny | Deny | C1 parametrize |
| ON | OFF | OFF | Deny | Deny | C1 + repo deny |
| OFF | ON | OFF | Deny | Deny | C1 |
| ON | ON | OFF | Allow writes* | Deny sync | C1 (*mocked env only) |
| ON | ON | ON | Allow* | Allow* | C1 (*mocked; no real write) |

Repository with `require_gates=True` raises `SignalCloudWriteDenied` when dual gate incomplete. Malformed/missing env fails closed (default false). No real env flags enabled.

---

## L. Cloud sync and idempotency simulations

Worker remains disabled. Offline behaviors covered by C1 + Phase 4D suites:

| Simulation | Result | Class |
| --- | --- | --- |
| Sync gated off | `skipped_reason=signal_cloud_sync_gated_off` | **VERIFIED WITH MOCKS** |
| Gates forced ON, owner unset | `signal_cloud_owner_user_id_unset` | **VERIFIED WITH MOCKS** |
| Successful delivery / duplicate / retry | Covered in `test_phase4d_*` | **VERIFIED WITH MOCKS** |
| Ambiguous commit before local ACK | Code refuses SYNCED until commit OK | **VERIFIED LOCALLY** (code review) |
| Live worker against Supabase | Not started | **N/A — forbidden** |

Intended boundary: mark local outbox `SYNCED` only after successful upsert (+ optional session commit). Partial cloud success without ACK remains retryable via idempotent keys / unique constraints.

---

## M. FastAPI security validation

Cloud routes under `/api/v1/signals/cloud`:

- `/status`, `/history`, `/history/{id}`, `/risk`, `/strategies`, `/analytics`, `/sync/health`
- Auth: `get_current_principal` / `require_private_catalog_access`
- Owner: JWT `sub` only
- Pagination capped (`limit` ≤ 200)
- Responses stamp `not_an_order` / `execution_allowed=false`
- Unauthenticated → 401; private-reads kill-switch → 403

Public market-data endpoints remain independent of cloud ownership. No side-effect POST write endpoints exercised.

---

## N. Next.js Agent Studio validation

`SignalsPanel` loads **local** SQLite history via existing signal proxies and displays sync **status badges** (`supabase writes OFF`, `auto-sync OFF`, pending/failed/synced counts, owner binding readiness). Copy states history is local until gated Supabase sync.

| Check | Result |
| --- | --- |
| No browser DB credentials | Pass |
| No automatic cloud-write trigger from UI | Pass (status/history only) |
| Misleading “synchronized” claim while gated | Not claimed; badges show OFF / never | Pass |
| Vitest | 32 passed |
| `npx tsc --noEmit` | exit 0 |

Cloud history JWT forwarding exists via shared auth helpers; live authenticated cloud-history UI against empty tables was **not** claimed as E2E PASS (private reads OFF + no Auth user creation).

---

## O. Least-privilege role design proposal (design only)

**Do not implement in C1.**

Proposed future architecture:

1. **`cryptonova_migrator`** — DDL/Alembic only; not used by API pool.
2. **`cryptonova_api_runtime`** — no `BYPASSRLS`, no superuser; `USAGE` on `app`; table privileges:
   - SELECT/INSERT/UPDATE on signal tables as needed for Gate C2+  
   - no TRUNCATE/REFERENCES/TRIGGER unless required  
3. Per-request: `SET LOCAL ROLE cryptonova_api_runtime` + `set_config('request.jwt.claim.sub', :sub, true)` (transaction-scoped), matching `session_identity.py` design.
4. Keep FORCE RLS review as a separate operator decision.
5. Pool must reset GUCs on checkout (`ConnectionIdentityGuard` model).

**Blockers today:** runtime uses pooler `postgres` credentials; switching requires new Supabase role secrets, connection string change, and regression of all SQLAlchemy paths — Gate C2+ / security remediation track, not C1.

---

## P. Local code changes

| Change | Defect | Fix |
| --- | --- | --- |
| `apps/api/app/migration_audit.py` | Full-suite flake: Phase 4D ORM tables flagged as “unexpected” once `cloud_models` registered | Whitelist `_PHASE4D_SIGNAL_TABLES`; add `audit_phase4d_signal_persistence_migration()` |
| `tests/test_phase4d_gate_c1_security.py` | Missing focused C1 offline coverage | Gate matrix, owner isolation, payload invariants, sync owner fail-closed, API 401/403, SQLite survival |
| `scripts/_gate_c1_readonly_catalog.py` | Need reproducible RO evidence | SELECT/catalog inspector (no DML) |
| This report | Deliverable | `docs/implementation/PHASE_4D_GATE_C1_SECURITY_VALIDATION_REPORT.md` |

No remote mutations. No write/sync/order flags enabled.

---

## Q. Test execution evidence

| Suite | Result |
| --- | --- |
| `tests/test_phase4d_gate_c1_security.py` | **11 collected / passed** (within focused batch) |
| Focused Phase 4D + 6A + auth + migration audits | **73 passed** |
| Full `uv run pytest tests/` | **465 passed**, 0 failed |
| `apps/web` Vitest | **32 passed** (8 files) |
| `apps/web` `tsc --noEmit` | **exit 0** |
| Live Supabase write tests | **Skipped / not run** (forbidden) |
| Live exchange order tests | **Skipped / not run** (forbidden) |
| Live Auth JWKS E2E | **NOT VERIFIED** |

---

## R. Remaining risks

1. **Privileged DB role with BYPASSRLS** — residual critical; app filters mandatory.
2. **No live Auth RLS E2E** — multi-tenant confidence incomplete for SaaS; acceptable for personal gated activation only with operator acceptance.
3. **Free-plan backup residual** — carried from Gate B; not re-litigated here.
4. **Owner binding for unattended sync** still requires future operator-set `SIGNAL_CLOUD_OWNER_USER_ID` (JWT sub) — unset today (correct).
5. SQLite signal_history count drifted 3→4 locally — expected for local SoT; cloud remains empty.

---

## S. Gate C1 decision

### **CONDITIONAL PASS**

All C1 objectives for **read-only remote verification**, **fail-closed gates**, **mocked isolation**, **payload/SQLite integrity**, and **offline automation** are met.

Conditionality is explicit because:

- Privileged `BYPASSRLS` role remains in use (**documented residual risk**).
- Real authenticated RLS/JWKS end-to-end cloud history is **NOT VERIFIED**.

This is permission to **request** separate Gate C2 approval — **not** permission to execute Gate C2.

---

## T. Gate C2 prerequisites

Before proposing/executing Gate C2 (controlled cloud writes):

1. Explicit operator approval for project `wmirifmgaftassgrfbyl` only.
2. Dual flags plan: enable `SIGNAL_SUPABASE_WRITES_ENABLED` + `SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED` under a written procedure (still keep sync OFF unless Gate D).
3. Bind `SIGNAL_CLOUD_OWNER_USER_ID` to a **real** verified Auth `sub` (do not invent UUIDs).
4. Confirm application-layer owner filters remain on every write path.
5. Prefer scheduling least-privilege role work before multi-user production; for personal single-owner C2, accept BYPASSRLS residual in writing.
6. Keep exchange order flags OFF; keep historical import OFF until Gate E.
7. Re-run C1-relevant offline suite immediately before first write.
8. Stop criteria: any unexpected cloud row count growth outside the approved write procedure → halt.

---

**STOP after Gate C1.** No Gate C2/D/E, no migration, no exchange orders.
