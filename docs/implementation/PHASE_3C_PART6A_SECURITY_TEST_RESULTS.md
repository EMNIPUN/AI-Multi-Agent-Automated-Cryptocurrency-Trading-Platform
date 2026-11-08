# Phase 3C Part 6A — Security Test Results

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Suite | `tests/test_phase3c_part6a_binding_api.py` + prior binding suite |
| Result | **28 passed** (11 Part 6A + 17 prior `test_exchange_bindings_phase3c.py`) |
| Cloud writes / Bybit / migrations | **None** |

---

## Matrix

| # | Requirement | Result |
|---|-------------|--------|
| 1 | Missing JWT rejected | **PASS** (401) |
| 2 | Invalid JWT rejected | **PASS** (401) |
| 3 | User A cannot read User B bindings | **PASS** (empty list + 404 inspect) |
| 4 | User A cannot revoke User B binding | **PASS** (404) |
| 5 | Client cannot spoof `owner_user_id` | **PASS** (422 `extra=forbid`) |
| 6 | Credential references validated | **PASS** (400 on inject / secret-shaped) |
| 7 | Pending cannot read private wallet data | **PASS** (kill switch + inactive) |
| 8 | Revoked cannot read private wallet data | **PASS** (inactive) |
| 9 | No API credentials leak to frontend DTO | **PASS** (alias only; no `credential_ref` key) |
| 10 | Private reads remain disabled | **PASS** (settings + list flags) |
| 11 | Live trading remains disabled | **PASS** (no trading routes; posture unchanged) |
| 12 | Duplicate pending handled safely | **PASS** (idempotent same id) |
| — | Mainnet create locked | **PASS** (403) |
| — | Fixture ACTIVE not marked live | **PASS** (`is_live_exchange_connection=false`) |

---

## Non-claims

- Real Auth E2E still **NOT PASS**.
- No live Bybit Testnet credential verification.
- No cross-tenant private wallet isolation claim (private reads off).
- No Postgres binding persistence.
