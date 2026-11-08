# Phase 3C Part 6D — Bybit Testnet Verification Adapter

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Real Bybit network calls | **None** |
| Binding activation | **None** |
| Private reads | **Disabled** |

---

## Adapter

Module: `apps/api/app/exchange/bybit_testnet_adapter.py`

| Component | Role |
|-----------|------|
| `BybitTestnetReadClient` | Protocol — read-only `fetch_account_identity` |
| `FakeBybitTestnetClient` | Deterministic injected fake (no sockets) |
| `BybitTestnetVerificationAdapter` | Ownership + Testnet + permission + response validation |
| `AdapterVerificationResult` | Structured outcome; `activates_binding=false`, `enables_private_reads=false` |

Reuses: credential registry, Part 6B gates / `activation_allowed_after_verification`, binding ownership APIs.

---

## HTTP (simulator only)

`POST /api/v1/exchange/bindings/{id}/simulate-verify`

- JWT owner required
- Always uses fake client (or `app.state.bybit_testnet_verify_client` injection)
- Updates fixture verification sim state for UI
- Binding status stays **pending** (never ACTIVE)

Next proxy: `/api/exchange/bindings/[id]/simulate-verify`

---

## UI

`/settings/exchanges` shows:

- Verification status badge
- Last verified timestamp
- Environment badge
- Safe simulator messages
- Explicit copy: simulated verify ≠ live Bybit / ≠ ACTIVE

---

## Prerequisites for real Testnet verification

1. Real Supabase Auth E2E PASS  
2. Least-privilege DB role applied  
3. Secure credential onboarding (vault)  
4. Operator approval for external Bybit calls  
5. Dual persistence gates + PENDING→ACTIVE workflow  
6. Separate Gate F for private reads  
