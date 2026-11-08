# Phase 3C Part 3 — Security baseline (repository audit)

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Scope | TASK 1–2 baseline: code paths, git/secret safety, known gaps |
| Migrations applied | **Not executed** by this phase |
| `PRIVATE_DATA_READS_ENABLED` | **false** (unchanged) |
| Commit / push | **Not performed** |

---

## Verified code paths

| Path | Role | Status |
|------|------|--------|
| `apps/api/app/auth/jwt_verifier.py` | JWT verify; rejects anon/service_role | OK |
| `apps/api/app/security/operator_local.py` | Loopback peer gate; rejects Auth + XFF | OK |
| `apps/api/app/exchange/bindings.py` | Enrollment + ownership authz | Hardened: allowlisted `credential_ref` only; inactive vs missing |
| `apps/api/app/exchange/binding_store.py` | In-memory + SQLAlchemy store | OK |
| `apps/api/app/exchange/credentials.py` | Allowlisted resolver; no dynamic env injection | Hardened |
| `apps/api/app/exchange/router.py` | Dual-path wallet reads | OK |
| `apps/api/app/observability/router.py` | Scope-filtered worker snapshot; SSE off | OK |
| `apps/web/src/lib/security/authenticated-proxy.ts` | JWT forward; break-glass gated | OK |
| `apps/web/src/lib/auth/browser-access-token.ts` | Supabase session preferred; interim storage fallback | Hardened |
| `agent/telemetry_ledger.py` | UUID telemetry scopes allowed | OK |

---

## Critical git/secret finding (fixed)

**Issue:** Root `.gitignore` contained bare `lib/`, which matched **`apps/web/src/lib/**`** via `git check-ignore`. Auth, security proxies, fixtures, and utils were **invisible to git** (not listed as untracked).

**Remediation:** Changed to root-only `/lib/` and `/lib64/`. Explicitly ignore `apps/web/.env.local`. After fix, `apps/web/src/lib/` appears as untracked and can be staged safely.

**Env:** `apps/web/.env.local` remains gitignored and contains local break-glass (`OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=true`). Must never ship to multi-user hosts.

**DATABASE_URL:** Not set in this audit shell — remote Alembic revision **not independently verified**. Do not assume `0001` is applied.

---

## Git checkpoint (non-destructive)

- Branch: `main` @ `345d3a1` tracking `origin/main`
- Large modified + untracked Phase 3B/3C delta
- **Do not** auto commit / stash / reset / clean

### Recommended staging groups (operator-approved later)

1. **gitignore + docs** — `.gitignore`, audit/runbook/reports  
2. **API security core** — `apps/api/app/exchange/*`, `apps/api/app/security/*`, models, routers, migration `0003`  
3. **Web lib + proxies** — `apps/web/src/lib/**`, wallet/snapshot routes  
4. **Agent Studio UI** — features/agent-studio + related components  
5. **Tests** — `tests/test_*phase3*`  

### Recovery guidance

- Keep working tree; copy or branch before any destructive op  
- Backup `.env` / `.env.local` outside the repo  
- Never force-add ignored secret files  

---

## Security issues / limitations

| Item | Severity | Notes |
|------|----------|-------|
| Migrations `0002`/`0003` unapplied | Blocker for prod private reads | Operator Gate C |
| `PRIVATE_DATA_READS` false | Intentional | Gate F |
| Local break-glass in `.env.local` | Local-only risk | Keep off shared deploys |
| Interim sessionStorage token | Medium | Supabase session preferred; storage is fallback |
| No remote DB revision probe | Info | `DATABASE_URL` unset here |
| SSE / order HTTP | OK (off/absent) | Must stay off |

---

## Required operator actions

See `PHASE_3C_PART3_OPERATOR_ACTIVATION_RUNBOOK.md` Gates A–G. No gated step executed in this phase.
