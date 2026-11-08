# Phase 4D — Owner Auth Design

## Interactive cloud history

- Bearer JWT verified (JWKS or HS256 server-side)  
- `require_private_catalog_access` → `PRIVATE_DATA_READS_ENABLED`  
- Owner UUID = `AuthenticatedPrincipal.user_id` (JWT `sub`)  
- Routes under `/api/v1/signals/cloud/*`

## Unattended sync owner binding

1. Operator authenticates in Supabase Auth (manual — no auto user creation).  
2. Copy the Auth user UUID (`sub`).  
3. Set `SIGNAL_CLOUD_OWNER_USER_ID=<uuid>` in server env only.  
4. Open Gates C/D only after DDL + verification.  

Invalid or missing binding → sync blocked (`signal_cloud_owner_user_id_unset` / `_invalid_uuid`).

## Never

- Invent UUIDs  
- Trust frontend-supplied owner ids  
- Create Auth users from the trading platform  
