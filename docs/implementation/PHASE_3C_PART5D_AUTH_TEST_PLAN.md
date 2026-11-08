# Phase 3C Part 5D — Real Auth E2E Test Plan

| Field | Value |
|-------|-------|
| Status | **PREPARED — AWAITING OPERATOR APPROVAL** |
| Project | `wmirifmgaftassgrfbyl` (development only) |
| Auth users created | **None yet** |
| Private reads during E2E | **Remain false** |

---

## 1. Disposable users (proposed)

Create **only** after approval, in development Auth (email provider):

| Alias | Email (example) | Purpose |
|-------|-----------------|---------|
| User A | `cryptonova.part5d.a+dev@example.com` | Auth + isolation subject A |
| User B | `cryptonova.part5d.b+dev@example.com` | Auth + isolation subject B |

Requirements:

- Development project only
- Strong unique passwords stored outside git (operator password manager)
- Confirm email if project requires it (or disable confirm for these two in Dashboard **only** if operator accepts that risk for disposable accounts)
- Tag in Auth user metadata: `{"cryptonova_probe":"phase3c_part5d"}` for cleanup identification

**Do not** use production emails or real customer accounts.

---

## 2. Scenario matrix

| # | Scenario | Auth expect | Authz expect (private reads OFF) |
|---|----------|-------------|-----------------------------------|
| 1 | User A signs in | Session + access_token | — |
| 2 | User B signs in | Session + access_token | — |
| 3 | Valid JWT → `GET /api/v1/me` | 200, `user_id` = A/B | `private_data_reads_enabled=false` |
| 4 | Expired JWT | 401 `token_expired` | — |
| 5 | Invalid signature | 401 | — |
| 6 | Wrong-project JWT | 401 `invalid_issuer` | — |
| 7 | Missing session / no Bearer | Next 401 `authentication_required` or FastAPI 401 | — |
| 8 | Service-role as Bearer | 401 `non_user_token` | — |
| 9 | User A → User B binding id | — | 403 after kill switch / or cross_tenant if reads on |
| 10 | User B → User A binding id | — | same |
| 11 | Pending/revoked binding | — | 403 `exchange_binding_inactive` **if** reads enabled + rows exist; else record kill-switch 403 |
| 12 | Session refresh | SDK refresh yields new access_token still accepted by `/me` | — |
| 13 | Break-glass | Remains false; unauthenticated wallet stays 401 | — |
| 14 | LIVE wallet vs SAMPLE | Wallet panel shows blocked/unavailable — **never** SAMPLE balances as LIVE | — |

### Kill-switch recording rule

While `PRIVATE_DATA_READS_ENABLED=false`, authenticated wallet/catalog calls that reach owner-bound paths **must** return **403** `ownership_schema_required`. Treat that as **expected authorization denial**, not test failure, and **not** as LIVE data success.

---

## 3. Planned commands (after approval — do not run now)

### 3.1 Identity guard

```powershell
$env:CRYPTONOVA_DB_TARGET="development"
$env:CRYPTONOVA_DEV_PROJECT_REF="wmirifmgaftassgrfbyl"
# Confirm PRIVATE_DATA_READS_ENABLED=false in .env
```

### 3.2 Sign-in (scripted; no secrets in repo)

Operator-local Node or Python using publishable key + email/password against  
`https://wmirifmgaftassgrfbyl.supabase.co/auth/v1/token?grant_type=password`  
→ capture access_token **in memory only** (never log).

### 3.3 FastAPI checks

```text
GET http://127.0.0.1:8000/api/v1/me
Authorization: Bearer <access_token_A>
→ 200

GET http://127.0.0.1:8000/api/v1/exchange/wallet
Authorization: Bearer <access_token_A>
→ 403 ownership_schema_required   # kill switch

GET http://127.0.0.1:8000/api/v1/me   # no header
→ 401
```

### 3.4 Next proxy checks

```text
GET http://localhost:3000/api/exchange/wallet   # no auth
→ 401 authentication_required
```

Browser: sign in User A → wallet panel shows blocked (not SAMPLE equity).

### 3.5 Negative JWT cases

Reuse offline HS256/JWKS unit tests already covering expired/wrong-iss/service_role; optionally re-hit live `/me` with tampered token → 401.

---

## 4. Optional synthetic bindings (separate sub-approval)

Only if operator wants scenarios 9–11 beyond the kill switch:

- Insert two **pending** / one **active** binding rows owned by A/B **or** use API in-memory store in a controlled test harness
- Prefer **no durable Bybit credential material**
- Cleanup: delete rows with attestation marker `phase3c_part5d_auth_e2e`

Default Part 5D path: **skip durable binding inserts**; prove Auth with `/me` + kill-switch 403s.

---

## 5. Cleanup

1. Sign out all probe sessions.
2. Delete Auth users A/B from Dashboard (or ban + delete).
3. Confirm no `phase3c_part5d` bindings remain (if any were created).
4. Confirm `PRIVATE_DATA_READS_ENABLED=false`, break-glass false.
5. Rotate publishable key only if it was exposed in logs (should not be).

---

## 6. Risks and limitations

| Risk | Mitigation |
|------|------------|
| Disposable users left behind | Metadata tag + cleanup checklist |
| Email confirmation friction | Operator configures Auth settings for these two only |
| Confusing 403 kill switch with Auth failure | Explicit matrix above |
| No login UI | Scripted Auth API or temporary approved UI |
| Class C ≠ API RLS | Documented; least-privilege role is separate |

---

## 7. STOP — operator approval request

Approve creation of the two disposable development Auth users and execution of this Class D plan by replying:

`APPROVE_AUTH_E2E_PART5D`

Confirm:

1. Project `wmirifmgaftassgrfbyl` only  
2. Emails (or authorize operator to choose `+dev` aliases)  
3. Auth redirect `http://localhost:3000/**` already set  
4. No private reads, no Bybit orders, no migrations, no git commit  
5. Cleanup obligation after tests  

**Do not create users until that reply.**
