# Phase 4D Gate C2 — Execution Plan (NON-EXECUTED)

| Field | Value |
| --- | --- |
| Status | **PROCEDURE ONLY — NOT EXECUTED** |
| Project | `wmirifmgaftassgrfbyl` |
| Preflight | `PHASE_4D_GATE_C2_PREFLIGHT_REPORT.md` |
| Authorization | Requires separate explicit operator approval |

**Do not run any step in §4–§7 until operator approval is on record.**  
**Do not enable write flags during preflight.**

---

## 1. Purpose

Perform **one** controlled synthetic cloud signal persistence into Supabase development project `wmirifmgaftassgrfbyl`, then verify with SELECT, then disable write gates.

Out of scope: Gate D sync worker, Gate E import, exchange orders, migrations, role DDL, multi-signal floods, HTTP write APIs.

---

## 2. Preconditions (checklist)

- [ ] Preflight status READY FOR SEPARATE APPROVAL
- [ ] Operator approval message names project `wmirifmgaftassgrfbyl`
- [ ] Operator chose **Option A** (stop) or **Option B** (BYPASSRLS exception)
- [ ] If Option A: **stop here** — do not continue
- [ ] If Option B: BYPASSRLS residual explicitly accepted
- [ ] Verified Auth `sub` available privately (JWKS-verified; not invented)
- [ ] Remote counts still 0/0/0/0/0 (re-check with RO catalog)
- [ ] `SIGNAL_CLOUD_SYNC_ENABLED` remains unset/false
- [ ] Exchange / live / auto-exec flags OFF
- [ ] `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false`
- [ ] No CloudSyncWorker running

---

## 3. Safety envelope

| Control | Required during C2 window |
| --- | --- |
| `SIGNAL_SUPABASE_WRITES_ENABLED` | `true` only for write moment |
| `SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED` | `true` only for write moment |
| `SIGNAL_CLOUD_SYNC_ENABLED` | **false** |
| `SIGNAL_CLOUD_OWNER_USER_ID` | verified UUID `sub` |
| Repository | `SqlAlchemySignalCloudRepository(session, require_gates=True)` |
| Method | `upsert_decision_payload` once, then optional idempotent second call |
| Scheduler upserts | **Do not call** `upsert_checkpoint` / `append_audit` |
| Worker | **Do not** start `CloudSyncWorker` |
| Orders | **Do not** call Bybit private order APIs |

Expected first-write deltas:

| Table | Expected Δ |
| --- | --- |
| `app.signal_history` | +1 |
| `app.signal_agent_contributions` | +3 |
| `app.signal_risk_events` | +1 |
| `app.scheduler_evaluation_history` | 0 |
| `app.scheduler_audit` | 0 |

Idempotent retry: +0 all tables.

---

## 4. Proposed commands (AUTHORIZED EXECUTION ONLY)

> Placeholders:  
> `<OWNER_SUB>` = verified Auth UUID  
> Do **not** commit real tokens or DATABASE_URL passwords into the repo or chat.

### 4.1 Read-only pre-write snapshot

```powershell
cd "E:\Financial Side\Trading\AI-Multi-Agent-Automated-Cryptocurrency-Trading-Platform"
uv run python scripts/_gate_c1_readonly_catalog.py
```

Abort if `db_ref_match` is false, alembic ≠ `20261107_0004`, or any Phase 4D count ≠ 0 (unless a prior approved synthetic already exists — then abort and replan).

### 4.2 Process-local gate arming (session only — prefer not writing `.env`)

```powershell
$env:SIGNAL_SUPABASE_WRITES_ENABLED = "true"
$env:SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED = "true"
$env:SIGNAL_CLOUD_SYNC_ENABLED = "false"
$env:SIGNAL_CLOUD_OWNER_USER_ID = "<OWNER_SUB>"
# Confirm exchange remains off — do not set AGENT_ALLOW_LIVE / order flags
```

### 4.3 Single synthetic write (proposed one-shot; create only under approval)

Proposed new script path (to be added **only when execution is approved**, if not already present):

`scripts/_gate_c2_synthetic_cloud_write.py`

Intended behavior (design contract):

1. Assert `DATABASE_URL` host maps to `wmirifmgaftassgrfbyl`.
2. Assert dual write gates true and sync false via `get_signal_cloud_gates()`.
3. Assert `SIGNAL_CLOUD_OWNER_USER_ID` parses as UUID and equals intended owner.
4. Build decision via `SignalPipeline` + fixture candles (no exchange orders).
5. Remap `decision_id` / `idempotent_key` / `correlation_id` to `c2synth_<hex>` family; stamp explanation/`reason_codes` with `GATE_C2_SYNTHETIC`.
6. Build `4D.1.0` payload; assert `execution_allowed is False` and `not_an_order is True`.
7. `configure_engine` → session → `SqlAlchemySignalCloudRepository(session, require_gates=True).upsert_decision_payload(owner_user_id=owner, payload=payload)`.
8. `session.commit()`.
9. Print **only**: decision_id, returned UUID, and contribution count planned — never JWT/DB URL.
10. Optional: second upsert same payload; assert same parent id.
11. Exit non-zero on any unexpected exception.

**Illustrative invoke (NOT RUN in preflight):**

```powershell
uv run python scripts/_gate_c2_synthetic_cloud_write.py --confirm-project wmirifmgaftassgrfbyl --confirm-synthetic GATE_C2_SYNTHETIC
```

Until that script exists under approval, do **not** improvise ad-hoc SQL INSERT.

### 4.4 Immediate gate disarm

```powershell
Remove-Item Env:SIGNAL_SUPABASE_WRITES_ENABLED -ErrorAction SilentlyContinue
Remove-Item Env:SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED -ErrorAction SilentlyContinue
# Keep SIGNAL_CLOUD_SYNC_ENABLED unset/false
# Optionally clear SIGNAL_CLOUD_OWNER_USER_ID after verification
$env:SIGNAL_SUPABASE_WRITES_ENABLED = "false"
$env:SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED = "false"
$env:SIGNAL_CLOUD_SYNC_ENABLED = "false"
```

If `.env` was edited (discouraged), restore write flags to unset/`false` immediately.

### 4.5 Read-only verification

```powershell
uv run python scripts/_gate_c1_readonly_catalog.py
```

Expect counts: history **1**, contributions **3**, risk **1**, scheduler tables **0** (for a clean baseline start).

Confirm `decision_id` like `c2synth_%` and `owner_user_id` matches `<OWNER_SUB>` via a SELECT-only helper or SQL editor — without dumping unrelated rows.

### 4.6 Offline regression after disarm

```powershell
uv run pytest tests/test_phase4d_gate_c1_security.py tests/test_phase4d_supabase_signal_persistence.py -q
```

---

## 5. Abort conditions

Stop immediately and disarm gates if:

- Project ref mismatch
- Alembic ≠ `20261107_0004`
- Sync flag true
- Owner UUID missing/invalid
- Payload fails `validate_decision_sync_payload`
- `execution_allowed` would be true
- Row counts after write ≠ expected
- Any scheduler table gains rows
- Integrity/unique errors that leave ambiguous state
- Any exchange/order code path is about to run

---

## 6. Cleanup (separate or included approval)

Default: **leave** synthetic rows labeled `GATE_C2_SYNTHETIC` for audit.

If cleanup is explicitly authorized in the same approval:

```sql
-- ONLY with explicit DELETE authorization; filter by synthetic id
-- DELETE FROM app.signal_agent_contributions WHERE decision_id = '<c2synth_id>';
-- DELETE FROM app.signal_risk_events WHERE decision_id = '<c2synth_id>';
-- DELETE FROM app.signal_history WHERE decision_id = '<c2synth_id>';
```

Prefer children-first deletes due to FKs. Re-verify counts afterward.

Without DELETE authorization: do not DELETE/UPDATE.

---

## 7. Evidence to capture in Gate C2 execution report

- Approval quote / Option A|B choice
- Pre/post counts
- `decision_id` (synthetic)
- Owner UUID prefix only (optional full UUID in private operator notes)
- Confirmation sync remained OFF
- Confirmation gates disarmed
- Pytest snippet after disarm
- Statement: no exchange orders

---

## 8. Explicit non-execution attestation (preflight)

Gate C2 preflight completed without:

- Enabling persistent write flags in `.env`
- Running `_gate_c2_synthetic_cloud_write.py` (script may not exist yet)
- INSERT/UPDATE/DELETE against Supabase signal tables
- Starting cloud sync
- Placing exchange orders

Await separate operator approval before §4.
