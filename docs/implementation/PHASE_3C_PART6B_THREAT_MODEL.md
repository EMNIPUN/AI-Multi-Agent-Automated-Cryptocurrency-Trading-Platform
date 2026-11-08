# Phase 3C Part 6B — Threat Model

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Scope | Binding APIs + credential onboarding design |

---

## Assets

- Supabase user JWTs / sessions
- Opaque credential / binding identifiers
- Future Bybit API key material (not present in this phase)
- Operator env-backed keys (`env:BYBIT_*`)

---

## Adversaries / misuse

| Threat | Mitigation (Part 6B) |
|--------|----------------------|
| Cross-user binding read/revoke | Owner checks; 404 on cross-tenant |
| Spoof `owner_user_id` | Forbidden on request body (`extra=forbid`) |
| Claim operator `env:` credentials via UI/API | **Hardened** → 403 `operator_credential_not_user_claimable` |
| Inject env var names via `credential_ref` | Allowlist + charset reject |
| Pending/revoked used for wallet | `require_active_binding_for_principal` deny |
| Mainnet premature binding | 403 `mainnet_binding_locked` |
| Secret leakage in responses/logs | Public view omits `secret_storage_ref`; redaction helper |
| Auto-activation after mock verify | Explicitly denied |
| Break-glass as multi-user auth | Remains disabled |
| BYPASSRLS postgres role | Documented residual risk — least-privilege still prerequisite |

---

## Vulnerabilities discovered in Part 6A audit

| ID | Finding | Severity | Disposition |
|----|---------|----------|-------------|
| V-6B-1 | User pending create accepted allowlisted `env:BYBIT_*` refs, allowing users to associate operator credential aliases with their pending bindings (not ACTIVE, but incorrect ownership signaling) | Medium | **Fixed** — user pending limited to `pending:*` |
| V-6B-2 | In-memory fixture store is process-local and resets on restart; UI could be misread as durable if banners ignored | Low | Mitigated by `persistence=fixture` + Auth E2E banner |
| V-6B-3 | FastAPI `postgres` BYPASSRLS still applies to any future persisted path | High (deferred) | Gate prerequisite — no persistence enabled |
| V-6B-4 | Auth E2E incomplete → JWT provenance for real users not fully proven | High (deferred) | Activation blocked on Auth E2E |

No critical secret exposure found in Part 6A responses (alias-only DTOs).

---

## Residual risks (accepted until later gates)

1. Real Auth E2E not PASS.
2. Privileged DB role.
3. No vault-backed secret store yet.
4. No live Testnet verification yet.
