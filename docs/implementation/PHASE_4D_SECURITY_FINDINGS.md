# Phase 4D — Security Findings (Read-Only)

## Critical advisory (known condition)

**Privileged `DATABASE_URL` bypasses RLS.**  
Evidence: Phase 3C DB role reviews; `PHASE_4D_SECURITY_REVIEW.md`; RLS policies target role `authenticated` only.

**Implication:** Application-layer `owner_user_id` filters are mandatory for FastAPI. Do not claim RLS protects privileged backend queries.

## Findings

| ID | Finding | Severity | Blocks DDL? | Blocks writes/sync? |
|----|---------|----------|-------------|---------------------|
| S1 | Privileged role BYPASSRLS | Critical advisory | No | Soft — require app filters forever until least-privilege role |
| S2 | Cloud history APIs not yet JWT-bound for Supabase reads | Medium | No | **Yes** before serving cloud history |
| S3 | Sync status endpoint unauthenticated (local personal) | Low | No | Review before multi-user |
| S4 | Gate env read via `os.getenv` (not only ApiSettings) | Low | No | Ensure process env is source of truth |
| S5 | Outbox summary cannot safely rebuild cloud row | Medium | No | **Yes** for sync enable |
| S6 | No INSERT/UPDATE RLS for `authenticated` | Info (good) | No | Keep Data API unexposed for `app` |

## JWT / ownership (code)

- `apps/api/app/auth/jwt_verifier.py` — JWKS; requires `exp`,`sub`,`iss`,`aud`; rejects bad audience  
- `principal_from_payload` — `user_id = sub`; rejects `anon` / `service_role`  
- Repository writes/reads take `owner_user_id: uuid.UUID` from caller — must be principal-derived at API boundary when wired

## Write gates (defaults OFF)

| Gate | Default | Startup bypass? |
|------|---------|-----------------|
| `SIGNAL_SUPABASE_WRITES_ENABLED` | false | No worker enables it |
| `SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED` | false | Dual gate required |
| `SIGNAL_CLOUD_SYNC_ENABLED` | false | `drain_outbox` not scheduled on lifespan |
| Binding persistence dual gates | false | Independent — untouched |
| `AGENT_ALLOW_LIVE` | false | Not a signal-cloud shortcut |
| `TESTNET_ORDER_SUBMISSION_APPROVED` | false | Phase 6A separate |
| `PERPETUAL_AUTO_EXECUTION_ENABLED` | false | Phase 6A separate |

`.env` currently sets `AGENT_ALLOW_LIVE=false`; signal-cloud keys absent → defaults false.

## Exchange execution isolation

Signal cloud path does not call Bybit private order APIs. Phase 6A automation remains SIGNALS_ONLY / submission gated.
