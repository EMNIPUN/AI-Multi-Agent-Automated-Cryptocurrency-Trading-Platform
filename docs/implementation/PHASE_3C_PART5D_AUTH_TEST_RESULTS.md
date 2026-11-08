# Phase 3C Part 5D — Auth Test Results

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Mode | Preflight + offline only (cloud Auth blocked) |

---

## Scenario results

| # | Scenario | Result | Evidence |
|---|----------|--------|----------|
| Pre | Dev identity / revision / kill switches | **PASS** | Live DB + env |
| Pre | Data API `app` not exposed | **PASS** | Prior operator verification |
| Pre | `/api/v1/me` exists | **PASS** | HTTP 401 without token |
| 1 | User A authenticates | **BLOCKED** | No admin key → users not created |
| 2 | User B authenticates | **BLOCKED** | Same |
| 3 | Valid JWT → FastAPI `/me` | **BLOCKED** | Needs real access tokens |
| 4 | Expired JWT rejected | **PASS (offline)** | `test_auth_phase2c` / Part 5B wiring |
| 5 | Invalid signature rejected | **PASS (offline)** | Same |
| 6 | Wrong-project issuer rejected | **PASS (offline)** | Same |
| 7 | Missing Bearer rejected | **PASS (live)** | `/api/v1/me` → 401; wallet proxy → 401 with break-glass off |
| 8 | Service-role as end-user rejected | **PASS (offline)** | `non_user_token` |
| 9–11 | Cross-user / pending-revoked bindings | **PASS (offline fixtures)** | Binding suites; not live DB rows |
| 9–11 live | Kill-switch wallet authz | **Not run with real JWT** | Expected later: 403 `ownership_schema_required` |
| 12 | Session refresh | **BLOCKED** | Needs real sessions |
| 13 | Break-glass disabled | **PASS** | Env + live 401 without token |
| 14 | LIVE wallet never SAMPLE | **PASS (code path)** | Wallet panel disabled/error; no SAMPLE equity injection |

---

## Created users

| Alias | Status |
|-------|--------|
| User A | **Not created** |
| User B | **Not created** |

Cleanup: **N/A** (nothing to delete).

---

## Offline counts this session

| Suite | Count |
|-------|-------|
| Auth + bindings + Part 5B wiring subset | **68 passed** |

---

## Distinction reminder

| Success type | Status |
|--------------|--------|
| Authentication (real Supabase JWT) | **Pending** |
| Authorization private LIVE data | **Intentionally disabled** (kill switch) |
| Offline ownership/bindings | **PASS** |
