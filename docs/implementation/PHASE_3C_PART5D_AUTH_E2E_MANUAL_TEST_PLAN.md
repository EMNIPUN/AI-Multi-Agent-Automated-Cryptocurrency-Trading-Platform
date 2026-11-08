# Phase 3C Part 5D — Manual Auth E2E Test Plan (No Service-Role)

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Project | `wmirifmgaftassgrfbyl` (development only) |
| Method | Normal signup / login / email confirmation via Auth UI |
| Service-role / secret key | **Not required** |
| Status | **PREPARED — AWAITING OPERATOR APPROVAL TO CREATE USERS** |
| Auth users created | **None** |
| Private reads during E2E | Must remain `PRIVATE_DATA_READS_ENABLED=false` |
| Exchange bindings | **None** (no synthetic writes) |
| Git commit/push | **None** |

---

## 0. Preconditions (local, already verified this session)

| Check | Result |
|-------|--------|
| Auth routes render | `/login` `/signup` `/forgot-password` `/reset-password` → HTTP 200 |
| Publishable client configured | `NEXT_PUBLIC_SUPABASE_URL` → `https://wmirifmgaftassgrfbyl.supabase.co` |
| Break-glass | `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false` |
| Private reads kill switch | `PRIVATE_DATA_READS_ENABLED=false` |
| Open-redirect helper | Unit tests PASS (`safeInternalPath`) |
| Offline JWT negatives | Pytest PASS (missing / wrong issuer / expired / non-user) |
| FastAPI missing Bearer `/me` | **401** (observed) |

**UI vs API:** `RequireAuth` is a **client-only** session gate. FastAPI independently verifies JWTs. Do not treat a rendered dashboard HTML 200 as authorization success.

---

## 1. Operator: Supabase redirect configuration (manual Dashboard only)

Do **not** change project-wide Auth settings from Cursor/scripts. In **Supabase Dashboard → Authentication → URL Configuration** for `wmirifmgaftassgrfbyl`, confirm:

| Setting | Expected |
|---------|----------|
| Site URL | `http://localhost:3000` |
| Redirect URLs allowlist | Includes `http://localhost:3000/**` |
| Email confirm callback | Lands on app (signup uses `emailRedirectTo` → `http://localhost:3000/login`) |
| Recovery callback | Lands on `http://localhost:3000/reset-password` |

Also confirm:

- Email provider can deliver to the two disposable addresses you control
- **Do not** disable “Confirm email” globally for this test
- **Do not** enable autoconfirm project-wide solely for convenience

App-side redirect safety (already coded):

- Post-login `?next=` → `safeInternalPath` (rejects absolute URLs, `//…`, auth-page loops)
- Recovery `redirectTo` → same-origin `/reset-password` only

---

## 2. Disposable users (operator-controlled emails)

Prefer **inbox-owned** addresses (Gmail `+` aliases OK). Placeholders only:

| Alias | Email (operator fills real inbox) | Purpose |
|-------|-----------------------------------|---------|
| User A | _operator disposable A_ | Signup → confirm → login → `/me` |
| User B | _operator disposable B_ | Signup → confirm → login → `/me` |

Passwords: strong unique values in operator password manager only. **Never paste passwords or JWTs into chat, logs, or git.**

Metadata suggestion (optional, via Dashboard after create): `{"cryptonova_probe":"phase3c_part5d"}` for cleanup.

### Approval gate

**STOP.** This plan does **not** authorize creating Auth users.

Reply exactly:

```text
APPROVE_AUTH_E2E_PART5D_MANUAL_SIGNUP
```

and list the two disposable emails you will use (or confirm you will create them yourself in the browser).

Only after that reply may the operator (or agent, under that approval) perform signup in the UI.

---

## 3. Scenario matrix (after approval)

| # | Scenario | How | Expect |
|---|----------|-----|--------|
| 1 | User A signup | `/signup` | Confirmation message if session null; no service-role |
| 2 | User A email confirm | Inbox link → allowlisted redirect | Account confirmed |
| 3 | User A login | `/login` | Session; redirect via safe `?next=` |
| 4 | User B signup + confirm + login | Same | Independent identity |
| 5 | `/api/v1/me` with User A JWT | Bearer from browser session (memory only) | **200**, `user_id` = A |
| 6 | `/api/v1/me` with User B JWT | Same | **200**, `user_id` = B; A ≠ B |
| 7 | Browser identity matches API | Compare Auth user id to `/me` | Match |
| 8 | Missing Authorization | `GET /api/v1/me` no header | **401** |
| 9 | Invalid JWT | Offline / crafted | **401** (pytest + optional live garbage token) |
| 10 | Wrong-project issuer | Offline pytest | **401** `invalid_issuer` |
| 11 | Logout | Shell / settings logout | Local session cleared; protected UI redirects to `/login` |
| 12 | Session refresh | Leave tab / `getSession` after refresh | New access token still accepted by `/me` |
| 13 | Protected pages unsigned | Open `/dashboard` logged out | Client redirect to `/login?next=…` |
| 14 | Next.js Bearer forward | DevTools: same-origin `/api/*` has `Authorization` when signed in | Present; break-glass unused |
| 15 | Break-glass remains off | Env check | `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false` |
| 16 | Private wallet reads blocked | With real JWT, authenticated wallet path | **403** kill-switch / ownership denial — **not** LIVE balances; **not** cross-tenant proof |

### Explicit non-claims

- Do **not** claim cross-user private-resource isolation is live-verified while private reads stay disabled.
- Do **not** create exchange bindings without a **separate** approval.
- Loopback FastAPI without `Authorization` may still hit **operator-local diagnostic** mode if wallet reads are enabled server-side — that is **not** the Next.js owner-bound path. Prefer verifying Next proxy (break-glass off → 401 without Bearer) and authenticated FastAPI with JWT → expected 403 under kill switch.

### Offline coverage (already runnable; no cloud users)

```text
pytest tests/test_phase3c_part5b_auth_wiring.py
pytest tests/test_phase3c_part5_security_preflight.py::test_jwt_rejects_wrong_issuer_and_expired
pytest tests/test_phase3c_part5_security_preflight.py::test_fastapi_missing_authorization_and_service_role
```

---

## 4. Cleanup (after Class D)

1. Delete disposable Auth users A and B in Dashboard (or mark disabled).
2. Confirm no binding rows were inserted.
3. Leave `PRIVATE_DATA_READS_ENABLED=false`.
4. Leave break-glass false.

---

## 5. Pass criteria for Class D

Class D may be marked **PASS** only when:

1. Two real Supabase-issued user JWTs were obtained via normal signup/login (or login after confirm).
2. Each JWT is accepted by FastAPI `/api/v1/me` with matching `user_id`.
3. Missing / invalid / wrong-issuer cases fail closed (live and/or offline as listed).
4. Logout + protected redirect observed.
5. Private reads and break-glass remain disabled; no LIVE wallet success claimed.

Until then: Class D = **NOT PASS**.
