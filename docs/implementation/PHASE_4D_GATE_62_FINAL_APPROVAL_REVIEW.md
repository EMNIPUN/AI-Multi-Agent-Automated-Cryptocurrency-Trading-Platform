# Phase 4D Gate 62 — Final Approval Review (PRE-EXECUTION)

| Field | Value |
| --- | --- |
| Gate | **62 final review — NOT AUTHORIZED TO EXECUTE** |
| Date | 2026-11-08 |
| Decision | **READY FOR EXPLICIT EXECUTION AUTHORIZATION** |
| Target | `wmirifmgaftassgrfbyl` |
| Current Alembic | `20261107_0004` |
| Proposed | `20261108_0005` |
| Remote mutations | **None** |

---

## 1. Executive summary

Independent re-review confirms: project identity, Alembic baseline, empty Phase 4D tables, and migration file integrity match Gate 61. SHA-256 **matches**. Proposed revision remains inactive. Local PG RLS evidence (Prompt 60 on PG 18) is compatible with remote **PostgreSQL 17.11** for the INHERIT/RLS behaviors relied upon.

Execution remains **forbidden** until a new operator message authorizes Gate 62 by project, revision, and checksum.

---

## 2. Project identity

| Check | Result | Criterion |
| --- | --- | --- |
| Project ref | `wmirifmgaftassgrfbyl` | **PASS** |
| Region host | `aws-0-ap-southeast-2.pooler.supabase.com` | **PASS** |
| Session user | `postgres` (`rolbypassrls=true`) | **PASS** (expected baseline) |

---

## 3. Migration checksum

| Item | Value |
| --- | --- |
| Path | `apps/api/alembic/versions_proposed/20261108_0005_option_a_least_privilege.py` |
| Size | 6804 bytes |
| Calculated SHA-256 | `9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a` |
| Gate 61 baseline | `9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a` |
| Match | **YES** |
| In active `versions/` | **No** |
| Criterion | **PASS** |

Imports: `alembic.op` only. No secrets. No DML. No DROP of existing authenticated policies.

---

## 4. Repository revision

| Item | Value |
| --- | --- |
| `git rev-parse HEAD` | `345d3a1f443ba9af57d5661154c33ae6facb99a7` |
| Branch | `main` tracking `origin/main` |
| Note | Working tree has unrelated local mods (e.g. `.env.example`); migration file hash verified independently of commit cleanliness |

---

## 5. Remote read-only inventory

| Object | State |
| --- | --- |
| Alembic | `20261107_0004` |
| Server version | **17.11** |
| Phase 4D counts | 0 / 0 / 0 / 0 / 0 |
| Table owners | all `postgres` |
| RLS | ON (not FORCE) on app tables except `alembic_version` |
| Policies | SELECT → `authenticated` only (unchanged) |
| `cryptonova_*` roles | **0** |
| `auth.uid()` | exists; postgres can EXECUTE |
| Cloud/trading flags | OFF |

Tools: `_gate_c1_readonly_catalog`, `_option_a_readonly_rls_inventory`, `_gate_61_readonly_role_probe`, `_gate_62_readonly_version_probe`.

---

## 6. Drift analysis

| vs Gate 61 | Drift? |
| --- | --- |
| Project / region / Alembic | No |
| Row counts | No |
| Policies / owners | No |
| cryptonova roles | Still absent |
| Migration checksum | No |

**Criterion: PASS — no unexpected drift.**

---

## 7. Role security review

### Proposed `cryptonova_api_runtime`

| Attribute | Design | Criterion |
| --- | --- | --- |
| NOSUPERUSER / NOBYPASSRLS / NOCREATEDB / NOCREATEROLE | Yes | **PASS** |
| INHERIT (base) | Yes — LOGIN members receive GRANTs | **PASS** (validated locally PG18; semantics same on PG17) |
| NOLOGIN base | Yes; LOGIN wrapper operator-created later | **PASS** |
| Table ownership | Must remain `postgres` | **PASS** (design) |
| DELETE | Not granted | **PASS** |
| DDL | Not granted | **PASS** |
| Schema | `USAGE` on `app` + `auth` | **PASS** (minimal for `auth.uid()`) |

### Proposed `cryptonova_migrator`

NOLOGIN, NOBYPASSRLS, DML + `CREATE ON SCHEMA app`. **Not** used as Alembic runner for this revision (see §9).

### Version note

Local Option A harness used disposable **PostgreSQL 18**; remote is **17.11**. Role INHERIT, RLS policy `TO role`, and `auth.uid()` GUC patterns relied upon are not 18-specific. Residual: live CREATE ROLE success on this Supabase plan remains **NOT VERIFIED** until apply.

---

## 8. RLS policy review

| Table | Proposed policies | USING / CHECK |
| --- | --- | --- |
| `signal_history` (+ contrib/risk) | SELECT/INSERT/UPDATE → runtime | `owner_user_id = auth.uid()` |
| Scheduler tables | SELECT → runtime | `owner_user_id = auth.uid()` |
| Catalog | SELECT → runtime | non-null owner = auth.uid(); bindings also `status='active'` |
| Existing `authenticated` SELECT | Untouched | Remain |

| Isolation property | Design | Evidence |
| --- | --- | --- |
| A cannot read/insert/update B | Policy + app filters | Local PG harness PASS; live Supabase under runtime **NOT VERIFIED** (Gate 63) |
| Missing `sub` | Empty/deny | Local PASS |
| Runtime subject to RLS | Non-owner + NOBYPASSRLS | Design PASS; enforcement after Gate 63 |
| Trust boundary | JWT verify in FastAPI → SET LOCAL GUC → auth.uid() | Documented; GUC alone not identity |

Scheduler stays SELECT-only — **PASS**.

---

## 9. Migrator privilege review

| Question | Answer |
| --- | --- |
| Who runs Gate 62 upgrade? | Current privileged Alembic connection (`postgres`) after promote — **same mechanism as Gate B** |
| Is `cryptonova_migrator` required to apply 0005? | **No** — it is created *by* 0005 |
| Can migrator ALTER postgres-owned tables later? | **No** without ownership/extra privilege — residual for future gates |
| Sufficient for this change mechanism? | **PASS** — privileged Alembic runner |

Do not elevate migrator to SUPERUSER/BYPASSRLS.

---

## 10. Migration atomicity

| Aspect | Assessment |
| --- | --- |
| Typical statements | CREATE ROLE (DO), GRANT, CREATE POLICY (idempotent DO), Alembic version update |
| Transactionality | Alembic/Postgres transactional DDL generally applies; role creation is recoverable via DROP/REVOKE if incomplete |
| Idempotency | Roles IF NOT EXISTS; policies existence-checked |
| Partial failure | Halt; REVOKE/DROP POLICY; leave roles until audited; do not cut over credentials |
| Downgrade | Revokes policies/grants; **does not DROP ROLE**; incomplete reversal |
| Execution mechanism | Promote file → `alembic upgrade 20261108_0005` under Gate B-style guards (`CRYPTONOVA_ALLOW_DEV_MIGRATIONS` window only) |

**Criterion: PASS** with documented incomplete downgrade for roles.

---

## 11. Backup / recovery assessment

| Item | Status |
| --- | --- |
| Supabase managed backup / PITR | **NOT VERIFIED** this review (no dashboard mutation/probe) |
| Free-plan residual | Previously accepted at Gate B for additive DDL |
| Signal rows at risk | **Zero** current counts |
| Logical recovery of security objects | Pre-change RO inventory + REVOKE/DROP POLICY procedures |
| API continuity on failure | Remains on `postgres` URL until Gate 63; SQLite SoT unaffected |

**Criterion: CONDITIONAL acceptance required in operator text** — not a design BLOCK for additive empty-table security DDL if operator explicitly accepts residual (same class as Gate B). Overall package remains READY with mandatory wording.

---

## 12. Exact proposed change manifest

| # | Object | Type | Op | Before | After | Reversible? |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `cryptonova_api_runtime` | ROLE | CREATE | absent | NOLOGIN NOBYPASSRLS INHERIT | Manual DROP after revoke |
| 2 | `cryptonova_migrator` | ROLE | CREATE | absent | same | Manual DROP after revoke |
| 3 | schema `app` | GRANT USAGE | GRANT | no cryptonova | runtime+migrator | REVOKE |
| 4 | schema `auth` | GRANT USAGE | GRANT | — | runtime | REVOKE |
| 5 | `auth.uid()` | GRANT EXECUTE | GRANT | — | runtime | REVOKE |
| 6 | signal write tables | GRANT S/I/U | GRANT | — | runtime | REVOKE |
| 7 | scheduler/catalog | GRANT SELECT | GRANT | — | runtime | REVOKE |
| 8 | listed tables | GRANT S/I/U/D | GRANT | — | migrator | REVOKE |
| 9 | schema `app` | GRANT CREATE | GRANT | — | migrator | REVOKE |
| 10 | `*_runtime_*` policies | POLICY | CREATE | absent | present | DROP POLICY |
| 11 | `app.alembic_version` | META | UPDATE | `20261107_0004` | `20261108_0005` | downgrade/stamp care |
| — | Signal rows | DATA | — | 0 | **0** | N/A |

**Excluded:** LOGIN secrets, FastAPI URL cutover, cloud writes, sync, import, orders, FORCE RLS, REASSIGN OWNED.

---

## 13. Read-only post-execution checks (future)

```text
uv run python scripts/_gate_c1_readonly_catalog.py
uv run python scripts/_option_a_readonly_rls_inventory.py
uv run python scripts/_gate_61_readonly_role_probe.py
uv run python scripts/_gate_62_readonly_version_probe.py
```

Expect Alembic `20261108_0005`, `cryptonova_roles≥2`, counts still 0, runtime policies present, authenticated policies intact, flags OFF, FastAPI still on postgres until Gate 63.

---

## 14. Local validation results

| Suite | Result |
| --- | --- |
| Option A + C1 + auth | **37 passed**, **1 skipped** (disposable PG :55432 down) |
| Prior Prompt 60 harness | 18/18 when cluster up |
| Flags | OFF |

---

## 15. Residual risks

1. Live CREATE ROLE / GRANT EXECUTE on this Supabase plan unproven until apply.
2. PITR/backup **NOT VERIFIED**.
3. Gate 62 does not remove FastAPI BYPASSRLS (Gate 63).
4. Future ALTER via `cryptonova_migrator` alone insufficient for postgres-owned tables.
5. Alembic downgrade does not DROP ROLE.

---

## 16. Decision

### **READY FOR EXPLICIT EXECUTION AUTHORIZATION**

Not permission to execute. Requires a **new** operator message matching the draft in `PHASE_4D_GATE_62_EXECUTION_APPROVAL_DRAFT.md`.

---

## 17. Draft operator authorization

See companion file — labeled **DRAFT ONLY — NOT OPERATOR APPROVAL**.

---

## 18. Non-execution attestation

This review performed no remote DDL/DML, no promote into `alembic/versions`, no credential cutover, no cloud writes, no exchange orders, no deploy, no git push.

### Acceptance criteria summary

| # | Criterion | Result |
| --- | --- | --- |
| 1 | Correct project | **PASS** |
| 2 | Correct Alembic baseline | **PASS** |
| 3 | SHA-256 unchanged | **PASS** |
| 4 | No schema drift | **PASS** |
| 5 | Role inheritance reviewed | **PASS** |
| 6 | Runtime NOBYPASSRLS design | **PASS** |
| 7 | RLS isolation design | **PASS** (live under runtime NOT VERIFIED) |
| 8 | Migrator sufficient for intended mechanism | **PASS** (postgres Alembic runner) |
| 9 | Atomic/failure reviewed | **PASS** |
| 10 | Recovery plan adequate | **CONDITIONAL** (operator must accept unverified PITR; inventory-based recovery) |
| 11 | Changes enumerated | **PASS** |
| 12 | Local tests | **PASS** |
| 13–16 | No remote mutate / cutover / writes / orders | **PASS** |
