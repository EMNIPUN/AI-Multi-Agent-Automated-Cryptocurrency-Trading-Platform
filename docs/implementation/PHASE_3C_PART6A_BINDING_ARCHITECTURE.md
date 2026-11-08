# Phase 3C Part 6A — Secure Bybit Binding Architecture

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Project | `wmirifmgaftassgrfbyl` |
| Alembic | `20261105_0003` (unchanged — no new migrations) |
| Persistence | **Disabled** (`EXCHANGE_BINDING_PERSISTENCE_ENABLED=false`) |
| Cloud DB writes | **None** |
| Real Bybit calls | **None** |

---

## 1. Lifecycle

| Status | Meaning | Wallet / private read |
|--------|---------|------------------------|
| `PENDING` | User-requested or operator-enrolled, not verified | Denied (`exchange_binding_inactive` or kill switch) |
| `ACTIVE` | Verified ownership + credential mapping | Allowed only if `PRIVATE_DATA_READS_ENABLED` + allowlisted ref |
| `REVOKED` | Owner or operator revoked | Denied |
| `ERROR` | Reserved for failed verification | Denied |

**Part 6A rule:** user self-serve API creates **PENDING only**. Transition to `ACTIVE` requires a future approved activation workflow (server-side credential ownership verification). No auto-activate.

---

## 2. Trust boundaries

```
Browser (/settings/exchanges)
  → Next.js /api/exchange/bindings* (Bearer forward; break-glass off)
  → FastAPI /api/v1/exchange/bindings*
       get_current_principal (JWT)
       owner_user_id := principal.sub   # never from body
       InMemory fixture store (default)
```

- Client cannot supply `owner_user_id` (`extra=forbid` on create body).
- Cross-tenant get/revoke returns **404** (no existence leak).
- `credential_ref` must be `pending:bybit-*` or allowlisted `env:BYBIT_*` — never raw secrets.
- Responses expose `credential_ref_alias` only — never keys/secrets.
- Fixture ACTIVE rows advertise `is_live_exchange_connection=false`.

---

## 3. Reused foundation (not duplicated)

| Component | Path |
|-----------|------|
| Domain model / enums | `apps/api/app/exchange/bindings.py` |
| Store protocol + InMemory / SQLAlchemy | `apps/api/app/exchange/binding_store.py` |
| Credential allowlist | `apps/api/app/exchange/credentials.py` |
| Ownership for wallet reads | `require_active_binding_for_principal` |
| Dual-path read context | `apps/api/app/exchange/access.py` |
| Table / RLS (prior) | Alembic `20261105_0003` |

---

## 4. Part 6A additions

| Piece | Path |
|-------|------|
| `request_pending_binding` / `revoke_owned_binding` | `bindings.py` |
| HTTP API | `apps/api/app/exchange/binding_api.py` |
| Settings flags | `EXCHANGE_BINDING_API_ENABLED`, `EXCHANGE_BINDING_PERSISTENCE_ENABLED` |
| Next proxies | `apps/web/src/app/api/exchange/bindings/**` |
| UI | `apps/web/src/app/settings/exchanges/page.tsx` |

### Endpoints

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/v1/exchange/bindings` | Bearer JWT |
| GET | `/api/v1/exchange/bindings/{id}` | Bearer JWT (owner only) |
| POST | `/api/v1/exchange/bindings` | Bearer JWT → PENDING |
| POST | `/api/v1/exchange/bindings/{id}/revoke` | Bearer JWT (owner only) |

Mainnet create → **403** `mainnet_binding_locked`.

---

## 5. Future secure credential onboarding (design only)

1. Operator or user initiates secret intake on a **server-only** channel (never Next public env / browser form for raw keys).
2. Encrypt at rest (KMS / Vault / Supabase vault) → mint opaque `credential_ref`.
3. Allowlist the ref; rotate by issuing a new ref and revoking the old binding.
4. Activation: prove key ownership against Bybit Testnet (signed read) → PENDING→ACTIVE.
5. Revocation: mark REVOKED + disable ref resolution.

**Not implemented in Part 6A.**

---

## 6. Persistence gate

`get_binding_management_store()`:

- `EXCHANGE_BINDING_PERSISTENCE_ENABLED=false` → always `exchange_binding_fixture_store` (in-memory).
- `true` → future path via `get_binding_store()` (SQLAlchemy) — **requires separate operator approval**.
