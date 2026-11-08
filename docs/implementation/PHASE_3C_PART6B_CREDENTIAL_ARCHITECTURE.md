# Phase 3C Part 6B — Credential Architecture

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Live secret intake | **Not implemented** |
| Real Bybit calls | **None** |
| Persistence | **Off** |

---

## 1. Ownership model

Each future credential record (`CredentialRecord`) carries:

| Field | Role |
|-------|------|
| Opaque credential `id` | Primary key |
| `owner_user_id` | Verified Supabase subject (or null if operator-unassigned) |
| `provider` / `environment` | Bybit + testnet/mainnet/demo |
| `public_ref` | Opaque alias (`cred:…` / `pending:…` / operator `env:…`) |
| `secret_storage_ref` | Vault/KMS/env pointer — **never** returned to browser |
| `permission_class` | Prefer `read_only`; trade/withdraw forbidden for onboarding |
| `verification_state` | unverified → verified / failed / revoked / rotated |
| Timestamps | created / rotated / revoked / last_verified |
| `exchange_account_fingerprint` | Non-secret identity after verify |

**Rule:** client-supplied `credential_ref` is never proof of ownership.

**Rule:** `env:BYBIT_*` operator refs are **not user-claimable**. User pending bindings may only use `pending:bybit-*`. Operator assignment remains `enroll_operator_binding` with attestation.

Implemented modules:

- `apps/api/app/exchange/credential_registry.py`
- `apps/api/app/exchange/credential_verification.py`
- Hardened `request_pending_binding` in `bindings.py`

---

## 2. Secure secret onboarding (design-only)

Future flow (not live in Part 6B):

1. Authenticated TLS request to a **server-only** intake endpoint (or operator channel).
2. Immediate encrypt / vault write → mint `secret_storage_ref` + `public_ref`.
3. Discard plaintext from memory; never write secrets to logs, telemetry, browser storage, or `NEXT_PUBLIC_*`.
4. Bind `owner_user_id` from JWT `sub` only.
5. Emit audit event: `credential_enrolled` with ids/env only.
6. Rotation: mark prior `ROTATED`, create successor UNVERIFIED, re-verify.
7. Revocation: `REVOKED` + disable resolution.

A browser-to-backend submission path may exist later, but raw secrets must never enter public env vars, client bundles, or application logs.

---

## 3. Bybit Testnet verification (design + mock)

`verify_testnet_credential_readonly` is fail-closed unless:

- Operator approval
- Auth E2E passed
- Binding persistence enabled
- External Bybit calls explicitly allowed
- Environment is Testnet
- Permission class is read-only

Even a successful mock verify **does not** activate a binding (`activation_requires_separate_operator_workflow`).

No trading permissions. No order placement. No mainnet verification path.

---

## 4. Binding API posture (unchanged gates)

| Flag | Value |
|------|-------|
| `EXCHANGE_BINDING_PERSISTENCE_ENABLED` | `false` |
| `PRIVATE_DATA_READS_ENABLED` | `false` |
| `AGENT_ALLOW_LIVE` | `false` |
| Break-glass | disabled |
