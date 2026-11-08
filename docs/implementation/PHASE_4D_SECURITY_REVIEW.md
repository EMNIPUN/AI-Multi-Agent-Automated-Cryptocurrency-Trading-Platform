# Phase 4D — Security Review

## Threat model (personal local app + Supabase)

| Risk | Mitigation |
|------|------------|
| Browser talks to DB | Forbidden — Next.js proxies FastAPI only; no service-role in frontend |
| Spoofed `owner_user_id` | Never accepted from client; derived from verified JWT `sub` |
| Cross-tenant reads | Application `WHERE owner_user_id = principal` on every query |
| RLS false confidence | Privileged `DATABASE_URL` **bypasses** RLS — documented; do not claim RLS alone protects FastAPI |
| Credential leakage into signal tables | Forbidden by design; bindings stay separate |
| Accidental cloud enable | Dual gates + DDL not applied until approval |
| Binding persistence coupling | Independent flags; binding gates remain false |

## Auth

- JWKS preferred (`AUTH_JWT_MODE=jwks`)
- Reject `anon` / `service_role` as principals
- Sync/history cloud endpoints that write must require authenticated principal (post-approval)

## Secrets

- `DATABASE_URL`, Bybit keys, `OPENAI_API_KEY` stay in gitignored server `.env`
- Sync status API must not echo passwords / service_role / API secrets (tested)

## Least privilege (still recommended, not applied)

See `apps/api/sql/runtime_role_recommendations.sql`. FastAPI should eventually use a non-BYPASSRLS role with matching RLS policies. Until then, app-layer filters are primary.

## Live trading / private exchange

Unchanged kill switches:
- `AGENT_ALLOW_LIVE=false`
- `PRIVATE_DATA_READS_ENABLED=false`
- `EXCHANGE_BINDING_PERSISTENCE_ENABLED=false`
- `EXCHANGE_BINDING_PERSISTENCE_OPERATOR_APPROVED=false`
