# Phase 3C Part 6C — Binding Persistence Architecture

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Cloud writes | **None** |
| Persistence runtime | **Disabled** (dual gate) |
| Alembic | `20261105_0003` unchanged / not re-run |

---

## 1. Audit summary (read-only)

| Control | Status |
|---------|--------|
| Owner from JWT `sub` only | **PASS** |
| Cross-user get/revoke → 404 | **PASS** |
| Duplicate pending idempotent (+ concurrency lock) | **PASS** |
| Pending/revoked never wallet-authorize | **PASS** |
| Fixture labeled `persistence=fixture` / not live | **PASS** |
| SqlAlchemy store exists but unused while gates false | **PASS** |
| Unique active indexes (cred + owner/env) in 0003 | **Present** |
| RLS SELECT-own for `authenticated` (active only) | **Present** (Data API defense; API still BYPASSRLS) |

---

## 2. Dual persistence gate (implemented)

Cloud-backed store is used only when **both** are true:

1. `EXCHANGE_BINDING_PERSISTENCE_ENABLED=true`
2. `EXCHANGE_BINDING_PERSISTENCE_OPERATOR_APPROVED=true`

Otherwise `get_binding_management_store()` always returns the in-memory fixture store.

Additional design gates (`PersistenceRuntimeGates`) before durable activation:

- Auth E2E passed
- Least-privilege DB role applied
- Explicit operator approval

---

## 3. Lifecycle states

`PENDING` → `ACTIVE` | `REVOKED` | `ERROR`  
`ACTIVE` → `REVOKED` | `ERROR`  
`ERROR` → `REVOKED` | `PENDING` (recovery)  
`REVOKED` → ∅ (terminal — no implicit reactivate)

Implemented offline in `binding_lifecycle.py`:

- Transaction begin/commit/rollback buffer
- Audit events (no secrets)
- Credential rotation demotes ACTIVE → PENDING
- `activate_fail_closed` never auto-enables private reads

---

## 4. Separated authorization stages

| Stage | Meaning | Part 6C |
|-------|---------|---------|
| 1. Credential enrolled | Secret behind storage ref | Design / registry offline |
| 2. Ownership verified | Testnet read-only mock | Fail-closed mock |
| 3. Binding durable | Postgres row | **Not enabled** |
| 4. Binding activated | status=ACTIVE | Fail-closed / separate workflow |
| 5. Private reads | `PRIVATE_DATA_READS_ENABLED` | **false** |

Verification success ≠ activation ≠ private reads ≠ trading.

---

## 5. Restart recovery

| Mode | After process restart |
|------|------------------------|
| Fixture (`persistence=fixture`) | Bindings **gone** (expected) |
| Future durable | Reload from `app.exchange_account_bindings`; revoked stay revoked |

---

## 6. Code touchpoints

| Module | Role |
|--------|------|
| `binding_api.get_binding_management_store` | Dual-gate fixture vs SQL |
| `binding_lifecycle.py` | Txn transitions + activation fail-closed |
| `security/session_identity.py` | Pool GUC reset design (offline) |
| `sql/runtime_role_recommendations.sql` | Role sketch (not executed) |
