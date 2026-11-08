# Phase 4D Gate C2 — Security Preflight & Controlled Cloud-Write Plan

| Field | Value |
| --- | --- |
| Gate | **C2 PREFLIGHT ONLY** |
| Date | 2026-11-07 |
| Project | `wmirifmgaftassgrfbyl` |
| Preflight status | **READY FOR SEPARATE APPROVAL** |
| Remote mutations this gate | **None** |
| Baseline | Gate C1 CONDITIONAL PASS — `PHASE_4D_GATE_C1_SECURITY_VALIDATION_REPORT.md` |

**This document does not authorize any Supabase write, sync, import, migration, exchange order, or deployment.**

Companion (non-executed): `PHASE_4D_GATE_C2_EXECUTION_PLAN.md`

---

## 1. Executive summary

Revalidated current environment against Gate C1. Project identity, revision `20261107_0004`, empty Phase 4D tables, fail-closed write/sync gates, and SQLite integrity remain consistent. Auth mode is JWKS with issuer/audience resolved to this project. `SIGNAL_CLOUD_OWNER_USER_ID` remains unset (correct for preflight).

A single-synthetic-write Gate C2 can be proposed using the gated SQLAlchemy repository (`upsert_decision` / `upsert_decision_payload`) with **automatic sync OFF**, **no HTTP write endpoint**, and **no CloudSyncWorker**.

**Residual risk:** runtime role `postgres` has `rolbypassrls=true`. Application-layer owner filters are mandatory. Operator must explicitly choose Option A (least-privilege first) or Option B (dev-only exception) before execution.

Offline regression: **69** focused Python tests passed; Vitest **32**; `tsc` exit **0**.

---

## 2. Current environment verification

| Check | Result | Class |
| --- | --- | --- |
| Project ref | `wmirifmgaftassgrfbyl` | VERIFIED REMOTELY |
| Host / region | `aws-0-ap-southeast-2.pooler.supabase.com` | VERIFIED REMOTELY |
| Alembic | `20261107_0004` | VERIFIED REMOTELY |
| Migration SHA-256 | matches approved Gate B digest | VERIFIED LOCALLY |
| Phase 4D table counts | all **0** | VERIFIED REMOTELY |
| `SIGNAL_SUPABASE_WRITES_ENABLED` | unset → OFF | VERIFIED LOCALLY |
| `SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED` | unset → OFF | VERIFIED LOCALLY |
| `SIGNAL_CLOUD_SYNC_ENABLED` | unset → OFF | VERIFIED LOCALLY |
| `SIGNAL_CLOUD_OWNER_USER_ID` | unset | VERIFIED LOCALLY |
| Exchange / live / auto-exec flags | OFF / unset | VERIFIED LOCALLY |
| `PRIVATE_DATA_READS_ENABLED` | `false` | VERIFIED LOCALLY |
| `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` | `false` | VERIFIED LOCALLY |
| Runtime DB role | `postgres`, `rolbypassrls=true`, `rolsuper=false` | VERIFIED REMOTELY |
| Auth mode | `jwks`, audience `authenticated` | VERIFIED LOCALLY |
| Issuer ends with | `…wmirifmgaftassgrfbyl.supabase.co/auth/v1` | VERIFIED LOCALLY |
| JWKS URL path | `/auth/v1/.well-known/jwks.json` | VERIFIED LOCALLY |
| FastAPI lifespan starts `CloudSyncWorker` | **No** | VERIFIED LOCALLY |
| SQLite schema / integrity | v4 / `ok` | VERIFIED LOCALLY |
| SQLite signal_history | 4 (local SoT; not cloud) | VERIFIED LOCALLY |

**Material delta vs C1:** none affecting safety. Cloud still empty; gates still OFF.

Secrets / URLs with credentials were not printed.

---

## 3. Gate C1 residual-risk review

| Residual | Still open? | C2 impact |
| --- | --- | --- |
| BYPASSRLS on runtime role | Yes | App owner filters must bind every write; RLS not protective for API role |
| Live Auth/JWKS E2E | Yes | Owner UUID must be obtained via operator-assisted verified session before write |
| Owner env unset | Yes (intentional) | Must bind only after JWT `sub` verification in execution gate |
| No prior cloud signal rows | Yes | Pre-write baseline remains zero — simplifies verification |

No unexpected critical regression vs C1.

---

## 4. Auth / JWT owner-binding readiness

### Verified controls (code)

- Owner for interactive APIs: verified JWT `sub` only (`assert_principal_matches_bound_owner`).
- Unattended sync owner: `SIGNAL_CLOUD_OWNER_USER_ID` must be a UUID; never invented by code.
- Never trust body/query/localStorage owner IDs on cloud history routes.
- JWKS path: signature + iss + aud + exp/nbf/iat; role allowlist `authenticated`; reject anon/service_role.

### Live session status

**No real authenticated session was used in this preflight** (Auth user creation/modification forbidden; no token capture).

**Missing prerequisite for execution:** operator must supply a verified Auth user UUID (`sub`) obtained from a successful JWKS-verified access token for project `wmirifmgaftassgrfbyl`.

### Operator-assisted procedure (later — do not run now)

1. Sign in via CryptoNova / Supabase Auth against `https://wmirifmgaftassgrfbyl.supabase.co` only.
2. Obtain access token in a private operator session (do not paste full JWT into chat/docs).
3. Verify offline with backend JWKS verifier (or a future approved helper that prints **only** `sub` prefix + full `sub` to a local secure operator console).
4. Confirm `iss` matches this project Auth issuer and `aud` includes `authenticated`.
5. Set `SIGNAL_CLOUD_OWNER_USER_ID=<that sub UUID>` only inside the approved execution window.
6. Never derive owner from email; never invent UUIDs; never commit the UUID to public docs if avoidable — reference as “operator-held verified sub”.

**Preflight assessment:** procedure is reliable; live binding **NOT VERIFIED** until operator completes steps under Gate C2 execution approval.

---

## 5. BYPASSRLS analysis

| Question | Finding |
| --- | --- |
| App owner filters on list/get/upsert? | Yes — every repository query includes `owner_user_id` |
| Nested contrib/risk scoped? | Yes — written with same `owner_user_id`; reads filter by owner |
| Direct repo bypass of gates? | `require_gates=False` exists for offline tests — **must not** be used for live C2 |
| HTTP write endpoint for signals? | **No** public cloud write API; history routes are GET |
| Controlled operator path? | Repository method + explicit session commit (scripted) preferred |
| Appropriate for multi-tenant prod? | **No** without least-privilege role |
| Acceptable for personal single-owner synthetic? | Only with explicit Option B acceptance |

---

## 6. Least-privilege remediation recommendation

### Option A — Preferred (separate security-change gate)

Create dedicated runtime role without `BYPASSRLS`, grant minimal table privileges, attach JWT `sub` via transaction-local GUC, switch FastAPI pool credentials. **Do not implement under this preflight.**

### Option B — Development-only exception

Allow **one** synthetic write under current `postgres` BYPASSRLS role after operator accepts residual risk in writing, with dual write gates, sync OFF, single verified owner, immediate gate disable, and read-only verification.

### Recommendation

- **Long-term / multi-user:** Option A before enabling ongoing cloud writes.
- **This personal development project / single synthetic C2:** preflight marks **READY FOR SEPARATE APPROVAL** contingent on **explicit Option A or Option B choice** in the operator approval text. Prefer Option A if the operator can schedule a security gate first; otherwise Option B is an acknowledged exception, not the default.

This preflight **does not choose Option B automatically**.

---

## 7. Cloud repository write-path audit

Path:

`CoordinatorDecision → build_decision_sync_payload (4D.1.0) → owner UUID → get_signal_cloud_gates → SqlAlchemySignalCloudRepository._upsert_public → PostgreSQL`

| Concern | Behavior |
| --- | --- |
| Gates | `_assert_write_allowed` when `require_gates=True` |
| Owner | Required `uuid.UUID` argument (caller-trusted; must be JWT `sub`) |
| Parent row | `app.signal_history` insert |
| Children | One contribution row per agent dict; one `signal_risk_verdict` risk event |
| Idempotency | Existing `(owner, decision_id)` returns prior id without re-insert; unique on `decision_id` and `(owner, idempotent_key)` |
| Integrity conflict | Rollback + re-select |
| Scheduler tables | **Not** touched by `upsert_decision*` |
| Sync worker | Independent; gated separately; not required for C2 |
| Execution invariants | Payload/decision keep `execution_allowed=false`, `not_an_order=true` |

Measured contribution count for standard pipeline fixture: **3** agents (`market_data`, `trend`, `momentum`) + **1** risk event row.

---

## 8. Proposed synthetic signal structure

| Field | Proposed value |
| --- | --- |
| Target project | `wmirifmgaftassgrfbyl` only |
| Owner | Verified Auth `sub` (operator-held) |
| Marker | `decision_id` prefix `c2synth_` + unique suffix; explanation/reason include `GATE_C2_SYNTHETIC` |
| Payload | `4D.1.0` from real `SignalPipeline.evaluate` then remapped ids |
| Symbol/TF | e.g. `BTCUSDT` / `linear` / `15` (fixture candles — not live trading) |
| `execution_allowed` | `false` |
| `not_an_order` | `true` |
| Sync | OFF |
| Import | OFF |
| Exchange | OFF |
| Invocation | Isolated operator script calling repository with `require_gates=True` — **not** auto worker |

Exact commands: see execution plan (non-executed).

---

## 9. Exact expected cloud row changes

**Baseline (current):** all five tables = 0.

**After one successful first write** (pipeline-shaped synthetic):

| Table | Δ rows | Notes |
| --- | --- | --- |
| `app.signal_history` | **+1** | Parent |
| `app.signal_agent_contributions` | **+3** | market_data, trend, momentum |
| `app.signal_risk_events` | **+1** | `event_type=signal_risk_verdict` |
| `app.scheduler_evaluation_history` | **0** | Not called |
| `app.scheduler_audit` | **0** | Not called |

**After immediate idempotent retry** (same `decision_id` / owner): **Δ = 0** additional rows; returns existing history UUID.

**Stop if:** any other table gains rows; counts exceed expected; wrong `owner_user_id`; `execution_allowed` truthy in stored JSON; unexpected symbols/ids.

---

## 10. Transaction and idempotency plan

1. Open SQLAlchemy session.
2. Call `upsert_decision_payload(..., require_gates=True)` inside session.
3. `commit()` only after flush succeeds.
4. On error: `rollback()`; leave gates; do not retry blindly.
5. Second call with same decision_id must not create children again (early return on existing parent).
6. Do not mark any SQLite outbox `SYNCED` unless a later gate explicitly includes sync (C2 should **not** drain outbox against cloud).

Ambiguous commit: treat as failure; verify with SELECT before any retry.

---

## 11. Read-only verification procedure

Post-write (execution gate only):

```sql
-- illustrative; run under read-only / SELECT after approved write
SELECT count(*) FROM app.signal_history;
SELECT count(*) FROM app.signal_agent_contributions;
SELECT count(*) FROM app.signal_risk_events;
SELECT count(*) FROM app.scheduler_evaluation_history;
SELECT count(*) FROM app.scheduler_audit;
SELECT decision_id, owner_user_id, symbol, action, risk_verdict
  FROM app.signal_history
 WHERE decision_id LIKE 'c2synth_%';
```

Confirm owner UUID matches verified `sub`; confirm contribution count = 3 and risk events = 1 for that `decision_id`.

Do not print secrets.

---

## 12. Recovery and cleanup procedure

| Step | Action |
| --- | --- |
| Pre-write snapshot | Record counts (expect 0/0/0/0/0) + project ref + alembic rev + owner prefix |
| On error before commit | Session rollback; disable both write flags; stop |
| Partial write suspicion | Compare counts to expected; if mismatch → halt; cleanup requires separate approval |
| After success | Disable `SIGNAL_SUPABASE_WRITES_ENABLED` and `SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED`; unset or leave owner env per operator preference; keep sync OFF |
| Cleanup DELETE/UPDATE | **Not authorized by C2 write approval unless explicitly included** — prefer leave synthetic rows labeled `GATE_C2_SYNTHETIC` until a cleanup approval |
| Evidence | Save redacted counts, decision_id, timestamps in Gate C2 execution report |

Committed rows are not automatically rolled back by PostgreSQL after success.

---

## 13. Test results (this preflight)

| Suite | Result |
| --- | --- |
| Phase 4D + C1 + auth + 6A focused pytest | **69 passed** |
| Vitest (`apps/web`) | **32 passed** |
| `tsc --noEmit` | **exit 0** |
| Live Supabase write tests | Not run (forbidden) |
| Live Auth E2E | NOT VERIFIED |

---

## 14. Security blockers

| Item | Blocks READY? | Blocks EXECUTION? |
| --- | --- | --- |
| BYPASSRLS residual | No if disclosed + Option A/B chosen | Yes until operator accepts Option B **or** completes Option A |
| Owner UUID unset | No (procedure documented) | Yes until verified `sub` bound |
| Dual write flags OFF | No | Must enable only under execution approval |
| Live JWKS E2E | Documented gap | Mitigate by verifying token at execution start |

No unexpected critical blocker beyond known C1 residuals.

---

## 15. GO / NO-GO recommendation

### **READY FOR SEPARATE APPROVAL**

Conditions for that approval text:

1. Project locked to `wmirifmgaftassgrfbyl`.
2. Explicit choice: **Option A** (defer C2 until least-privilege) **or** **Option B** (accept BYPASSRLS for one synthetic write).
3. Verified owner `sub` binding procedure completed privately.
4. Dual write gates ON only for the approved window; sync/import/orders remain OFF.
5. Scope limited to one synthetic `c2synth_*` decision (+ 3 contrib + 1 risk) via gated repository script.
6. Immediate gate disable + read-only verification afterward.

**READY ≠ authorized to execute.**

---

## 16. Explicit operator approval requirements

Paste/adapt:

> I authorize Gate C2 **execution** for CryptoNova development project `wmirifmgaftassgrfbyl` only.  
> I choose **[Option A — stop / remediate first | Option B — accept BYPASSRLS residual for one synthetic write]**.  
> I will supply a verified Auth JWT `sub` as `SIGNAL_CLOUD_OWNER_USER_ID` without inventing UUIDs.  
> Scope: one `GATE_C2_SYNTHETIC` signal via gated repository; expected +1/+3/+1/+0/+0 rows; sync OFF; import OFF; exchange orders OFF.  
> Cleanup DELETE is **[not authorized | authorized with decision_id filter …]**.  
> Dual write flags must be disabled immediately after the test.

Until that message exists, **do not enable write flags and do not run the execution plan.**
