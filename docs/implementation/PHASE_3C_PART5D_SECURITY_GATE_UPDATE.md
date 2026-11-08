# Phase 3C Part 5D — Security Gate Update (Manual Signup Path)

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Full security gate | **NOT PASS** |
| Class D (real Auth E2E) | **NOT PASS** |
| Delta vs prior Part 5D summary | Manual no-service-role E2E path prepared; local UI re-verified; cloud users still none |

---

## Scoreboard

| Item | Result |
|------|--------|
| Auth architecture | **PASS** |
| Auth UI routes | **PASS** (local render + open-redirect unit tests) |
| Supabase redirect Dashboard config | **Operator checklist ready** (not auto-changed) |
| Real user JWT → FastAPI `/me` | **NOT RUN** |
| Session login / logout / refresh (live) | **NOT RUN** |
| JWT negatives (missing / invalid / wrong issuer) | **PASS** (live missing + offline suite) |
| Next.js break-glass | **PASS** (disabled) |
| Private wallet reads | **DISABLED** (`PRIVATE_DATA_READS_ENABLED=false`) |
| Cross-tenant private isolation (live) | **Not claimed** |
| Class C RLS | **PASS** (prior) |
| Auth users created | **NONE** |
| Service-role required for remaining path | **No** (signup + email confirm) |
| Migrations / grants / bindings / Bybit / git | **NONE** |

---

## What changed this prompt

1. Documented **manual signup E2E** that does **not** need a service-role key.
2. Re-verified Auth pages return 200; `/api/v1/me` without Bearer returns 401.
3. Re-ran auth helper vitest (**10**) and selected FastAPI JWT pytest (**11**).
4. Explicit **STOP** before any cloud user creation.

---

## Remaining blockers for Class D PASS

1. Operator reply: `APPROVE_AUTH_E2E_PART5D_MANUAL_SIGNUP` + two disposable emails (or self-create confirmation).
2. Confirm Dashboard Site URL `http://localhost:3000` and allowlist `http://localhost:3000/**`.
3. Execute signup → email confirm → login for Users A and B.
4. Verify each real JWT against `/api/v1/me`; record browser/API id match.
5. Observe logout + protected redirect + refresh with those sessions.
6. Confirm authenticated private reads still **403** under kill switch (no LIVE success; no isolation claim).

If confirmation email cannot be delivered: stop and report — do **not** disable email confirmation globally.

---

## Related documents

| Doc | Purpose |
|-----|---------|
| `PHASE_3C_PART5D_AUTH_E2E_MANUAL_TEST_PLAN.md` | Operator steps + approval gate |
| `PHASE_3C_PART5D_AUTH_E2E_RESULTS.md` | Exact results this session |
| `PHASE_3C_PART5D_AUTH_UI_IMPLEMENTATION.md` | Auth UI implementation |
| `PHASE_3C_PART5D_GATE_SUMMARY.md` | Prior gate rollup |
| `PHASE_3C_PART5D_SECURITY_GATE_UPDATE.md` | This update |
