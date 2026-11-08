# Phase 3C Part 5D — Auth E2E Results (No Service-Role Path)

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Project | `wmirifmgaftassgrfbyl` |
| Class D | **NOT PASS** |
| Cloud Auth users created | **NONE** |
| Service-role used | **NONE** |
| Migrations / role grants / bindings / Bybit / git | **NONE** |

---

## 1. Local Auth UI verification (this session)

| Route / check | Result | Notes |
|---------------|--------|-------|
| `GET /login` | **200** | Renders |
| `GET /signup` | **200** | Renders |
| `GET /forgot-password` | **200** | Renders |
| `GET /reset-password` | **200** | Renders |
| `GET /dashboard` (unsigned SSR) | **200** | HTML loads; `RequireAuth` client-redirects — **not** API authz |
| `?next=https://evil.example` / `//evil` | Page **200** | Client uses `safeInternalPath` → fallback `/dashboard` (unit-tested) |
| `?next=/agents/live` | **200** | Allowed internal path shape |
| Publishable Supabase URL | Configured | Matches development project |
| Break-glass | **false** | `OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false` |
| Private reads | **false** | `PRIVATE_DATA_READS_ENABLED=false` |

Session persistence / refresh / logout with a **real** user: **NOT EXECUTED** (no disposable users yet).

---

## 2. Redirect configuration

| Item | Status |
|------|--------|
| App recovery redirect target | Code: `{origin}/reset-password` |
| App email confirm redirect | Code: `{origin}/login` |
| Dashboard Site URL / allowlist | **Operator must confirm manually** — not changed by agent |
| Open-redirect unit tests | **10** auth/security helper tests PASS (`safe-redirect`, `map-auth-error`, `operator-proxy-gate`) |

---

## 3. FastAPI / offline authz (no real user JWT yet)

| Check | Result |
|-------|--------|
| `GET /api/v1/me` without Authorization | **401** (observed this session) |
| Wrong issuer / expired / non-user / missing auth (pytest) | **11 passed** (wiring + selected preflight) |
| Prior JWT offline subset (Part 5D UI task) | **24 passed** |
| Authenticated wallet with kill switch | Deferred until real JWT; expect **403**, not LIVE data |
| Cross-user private isolation (live) | **Not claimed** (private reads disabled; no bindings) |

---

## 4. Real Supabase Auth E2E matrix

| # | Scenario | Status |
|---|----------|--------|
| 1–4 | User A/B signup, confirm, login | **BLOCKED** — awaiting operator approval + disposable emails |
| 5–7 | `/me` accepts real JWTs; browser/API id match | **NOT RUN** |
| 8 | Missing Authorization → 401 | **PASS** (live `/me`) |
| 9–10 | Invalid / wrong-project JWT | **PASS** (offline pytest) |
| 11–13 | Logout, refresh, protected redirect | **NOT RUN** (needs real session) |
| 14–15 | Bearer forward; break-glass off | Break-glass **PASS** (env); Bearer forward **NOT RUN** live |
| 16 | Private wallet reads blocked | Kill switch armed; live JWT case **NOT RUN** |

---

## 5. Blockers

1. **Operator approval** required before creating any cloud Auth users (`APPROVE_AUTH_E2E_PART5D_MANUAL_SIGNUP`).
2. **Two disposable, inbox-controlled emails** (confirmation delivery required).
3. **Dashboard redirect allowlist** confirmation for `http://localhost:3000/**`.
4. If confirmation mail cannot be delivered: report blocker — **do not** disable email confirmation globally.

Service-role / Admin `createUser` is **not** required for this path.

---

## 6. Security posture retained

- No service-role in browser or agent workflows for this prompt
- No Auth bypass / sessionStorage substitute
- No DB migrations, grants, binding writes, Bybit orders, or git push
- Private reads remain disabled; live trading remains disabled
