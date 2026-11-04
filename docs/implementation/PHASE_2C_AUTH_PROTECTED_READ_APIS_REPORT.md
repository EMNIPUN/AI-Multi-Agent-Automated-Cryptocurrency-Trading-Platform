# Phase 2C — Supabase Auth & Protected Read-Only APIs

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Project | CryptoNova |
| Scope | Fail-closed JWT auth + protected GET contracts |
| Private DB rows | **Not exposed** until ownership/RLS (`PRIVATE_DATA_READS_ENABLED=false`) |
| Trading HTTP | Still disabled |
| Offline suite | See verification below |

---

## Files created / changed

### Created
| Path | Role |
|------|------|
| `apps/api/app/auth/principal.py` | `AuthenticatedPrincipal` |
| `apps/api/app/auth/errors.py` | `AuthError` / `AuthConfigError` |
| `apps/api/app/auth/jwt_verifier.py` | JWKS + HS256 verifiers, test double |
| `apps/api/app/ownership.py` | Deny-by-default catalog gate + same-user helper |
| `apps/api/app/routers/me.py` | `GET /api/v1/me` |
| `apps/api/app/routers/catalog.py` | decisions / events / strategies contracts |
| `apps/api/sql/ownership_rls_plan.sql` | Future owner column + RLS sketch (not applied) |
| `tests/test_auth_phase2c.py` | Offline auth/authorization tests |
| `docs/implementation/PHASE_2C_AUTH_PROTECTED_READ_APIS_REPORT.md` | This report |

### Updated
| Path | Change |
|------|--------|
| `apps/api/app/config.py` | Supabase Auth settings; `PRIVATE_DATA_READS_ENABLED` |
| `apps/api/app/deps.py` | Bearer auth; verifier injection; ownership dependency |
| `apps/api/app/factory.py` | Mount me/catalog; CORS `Authorization` |
| `apps/api/app/schemas.py` | `MeResponse`, pagination, status auth flags |
| `apps/api/app/routers/system.py` | Auth configuration flags on status |
| `.env.example` | Auth placeholders (no secrets) |
| `pyproject.toml` / `uv.lock` / `requirements.txt` | `PyJWT[crypto]` |

SQLite execution/risk SoT and Bybit credentials: **unchanged**.

---

## Supabase JWT verification mechanism

| Mode | When | Behavior |
|------|------|----------|
| **`jwks` (default)** | Prefer for current Supabase asymmetric signing | Fetch JWKS from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`; allow **ES256/RS256** only; verify signature, `iss`, `aud`, `exp`, `nbf`, `iat`, `sub` |
| **`hs256` (legacy)** | Only if project still uses legacy JWT secret | Server-side `SUPABASE_JWT_SECRET` only; algorithm **HS256** only; same claim checks |

Additional rejects:

- Missing/malformed Bearer token  
- `role` in `{anon, service_role}` or not `authenticated`  
- Missing `sub`  
- JWKS/key errors → **503** (`jwks_unavailable`) — fail closed  
- Never trust `X-User-Id` or other client identity headers  
- Tokens/secrets never logged or returned  

Tests inject `app.state.token_verifier` (`StaticMappingVerifier`) for deterministic offline runs without contacting Supabase.

---

## Protected endpoint contracts

| Method | Path | Auth | Authorization / data |
|--------|------|------|----------------------|
| GET | `/health` | None | Public liveness |
| GET | `/api/v1/system/status` | None | Non-secret flags only |
| GET | `/api/v1/me` | Bearer user JWT | Verified `user_id` / `role` / optional email |
| GET | `/api/v1/agents/decisions` | Bearer | **403 `ownership_schema_required`** unless `PRIVATE_DATA_READS_ENABLED` |
| GET | `/api/v1/system/events` | Bearer | Same ownership gate |
| GET | `/api/v1/strategies` | Bearer | Same ownership gate |

Pagination: `limit` ∈ [1,100], `offset` ≥ 0 (422 on violation).

Even if `PRIVATE_DATA_READS_ENABLED=true`, Phase 2C handlers return **empty `items`** — they do **not** query shared `app.*` tables yet (no ownership columns).

---

## Database privacy and RLS plan

1. Keep schema `app` **out** of Supabase Data API Exposed schemas.  
2. Reviewed revoke script remains manual: `apps/api/sql/revoke_public_api_access.sql` (not auto-run).  
3. Future ownership: `apps/api/sql/ownership_rls_plan.sql` (`owner_user_id` + RLS + FastAPI filter by `principal.user_id`).  
4. Per-request SQLAlchemy sessions; no cross-request role leakage.  
5. No elevated Supabase secrets in frontend / `NEXT_PUBLIC_*`.

---

## Offline test results

```text
uv run pytest -q
145 passed
```

Coverage includes: missing auth, valid user token, expired/invalid signature/issuer/audience, unsupported alg, missing sub, service_role, JWKS failure, ownership 403, pagination bounds, public health/status, empty catalog when flag enabled.

---

## Remaining risks

1. Enabling `PRIVATE_DATA_READS_ENABLED` without ownership columns would still not dump DB rows in 2C handlers, but must stay **false** until RLS + filters exist.  
2. Mis-set `SUPABASE_URL` / issuer breaks verification (fail closed 503/401).  
3. HS256 mode is weaker operationally if secret leaks — prefer JWKS.  
4. Dashboard Exposed schemas still human-confirmed.  
5. No Next.js yet — token acquisition is out of band for API-only phase.

---

## Next steps (ownership + Phase 3 dashboard)

1. Alembic revision adding `owner_user_id` (+ indexes) to `app.*` tables.  
2. Enable RLS policies; keep Data API unexposed or tightly scoped.  
3. Implement authorized SELECT in catalog routers filtered by `principal.user_id`.  
4. Flip `PRIVATE_DATA_READS_ENABLED` only after tests prove isolation.  
5. Phase 3: Next.js with Supabase Auth client; API uses user access JWT only (never service role in browser).

---

## Success checklist

| Criterion | Status |
|-----------|--------|
| Fail-closed user JWT validation | Pass |
| No cross-tenant row API yet | Pass (403 / empty) |
| Real private rows inaccessible | Pass |
| Protected GET contracts present | Pass |
| Trading safety / SQLite SoT unchanged | Pass |
| Offline tests | **145 passed** |
