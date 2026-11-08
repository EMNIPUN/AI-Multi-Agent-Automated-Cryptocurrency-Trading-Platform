# Phase 3C Part 6C — Database Security Review

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Role / grant changes | **None** |
| Migrations executed | **None** |

---

## 1. Current connection risk

| Item | Finding |
|------|---------|
| Role | `postgres` via session pooler |
| `BYPASSRLS` | **true** |
| Per-request JWT GUC / `SET ROLE` | **Not used** |
| Consequence | RLS does not constrain FastAPI SQL; app `WHERE` + JWT authz remain primary |

---

## 2. Least-privilege target (design only — not applied)

| Role | Purpose |
|------|---------|
| Migration / operator | Alembic DDL; elevated; never FastAPI pool |
| `cryptonova_api_runtime` | App DML; **no** `BYPASSRLS` |

Proposed privileges for bindings (sketch in `runtime_role_recommendations.sql`):

- `USAGE` on schema `app`
- `SELECT, INSERT, UPDATE` on `app.exchange_account_bindings` (prefer no `DELETE`)
- Matching RLS policies `TO cryptonova_api_runtime` using transaction-local owner GUC
- No grants to `anon` / browser Data API on `app`

---

## 3. Identity propagation & pool isolation

Design (offline model: `ConnectionIdentityGuard`):

1. Verify JWT in FastAPI → trusted `user_id`
2. Checkout pool connection → **reset** prior GUCs
3. `SET LOCAL` / `set_config(..., true)` for owner claim inside transaction
4. Run ownership-filtered SQL
5. Release → clear identity again

**Prevents:** tenant identity leakage across pooled connections.

Until least-privilege role ships, do **not** enable durable binding writes.

---

## 4. Required future database changes (operator-approved later)

1. Create `cryptonova_api_runtime` (no BYPASSRLS)
2. Grant schema/table privileges as above
3. Add RLS policies for that role (owner_user_id)
4. Point `DATABASE_URL` FastAPI pool at runtime role (migration URL stays elevated)
5. Optional: partial unique index for non-revoked pending per owner/env
6. Wire session GUC helpers in request middleware

**Not done in Part 6C.**

---

## 5. Residual risks

| Risk | Severity | Mitigation now |
|------|----------|----------------|
| BYPASSRLS app role | High | Persistence dual-gated off |
| `store.get(id)` without owner assert | Medium | Binding API uses `get_owned_binding` |
| Fixture mistaken for durable | Low | `persistence=fixture` + UI banners |
| Auth E2E incomplete | High | Activation / persistence blocked |
