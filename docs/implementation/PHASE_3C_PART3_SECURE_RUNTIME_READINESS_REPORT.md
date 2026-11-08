# Phase 3C Part 3 — Secure Runtime Readiness Report

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Scope | Operator-controlled activation readiness; local hardening; offline verification |
| Migrations applied | **None** (preflight only) |
| `PRIVATE_DATA_READS_ENABLED` | **false** (unchanged) |
| `OBSERVABILITY_LIVE_STREAM_ENABLED` | **false** |
| Real order HTTP | **Absent** |
| Git commit / push | **Not performed** |

---

## 1. Executive summary

CryptoNova is **code-ready and offline-tested** for an operator-controlled, ownership-verified **read-only** activation. Private reads, SSE, remote migrations, and real-money trading remain **off**. A critical `.gitignore` bug that hid `apps/web/src/lib/**` from git was fixed. Credential enrollment is allowlist-only. Session resolution prefers Supabase Auth over interim `sessionStorage`.

| State | Status |
|-------|--------|
| Code implemented | **Yes** (Part 3 hardening + prior Part 1–2) |
| Offline tested | **Yes** — 256 pytest / 15 Vitest / typecheck / lint / build |
| Runtime verified (migrated DB + private reads) | **No** — operator Gates C–G pending |
| Operator approval pending | **Yes** |
| Production activated | **No** |

---

## 2. Files changed (Part 3)

| Path | Change |
|------|--------|
| `.gitignore` | Root-only `/lib/`; ignore `apps/web/.env.local` |
| `apps/api/app/exchange/bindings.py` | Allowlisted enrollment; inactive vs missing |
| `apps/api/app/exchange/credentials.py` | Injection guards; `is_allowlisted_credential_ref` |
| `apps/web/src/lib/auth/browser-access-token.ts` | Supabase session preferred; sign-out helper |
| `apps/web/src/lib/security/authenticated-proxy.ts` | No XFF forward; redirect error |
| `apps/web/src/components/WalletBalancePanel.tsx` | Auth UX; null ≠ zero |
| `apps/web/src/features/agent-studio/hooks/use-agent-snapshot.ts` | Async auth headers |
| `tests/test_phase3c_part3_runtime_readiness.py` | Isolation matrix |
| `tests/test_exchange_bindings_phase3c*.py` | Allowlist-compatible fixtures |
| `docs/implementation/PHASE_3C_PART3_SECURITY_BASELINE.md` | Baseline audit |
| `docs/implementation/PHASE_3C_PART3_OPERATOR_ACTIVATION_RUNBOOK.md` | Gates A–G |
| `docs/implementation/PHASE_3C_PART3_SECURE_RUNTIME_READINESS_REPORT.md` | This report |

---

## 3. Git / secret safety findings

- Branch `main` @ `345d3a1`; large uncommitted Phase 3B/3C delta retained (not discarded).
- **Critical:** bare `lib/` in `.gitignore` ignored `apps/web/src/lib/**` — **fixed** to `/lib/`.
- `apps/web/.env.local` gitignored; contains local break-glass only.
- `DATABASE_URL` unset in audit shell → remote Alembic revision **not verified**.
- No secrets printed; no auto commit/push/stash/reset.

Recommended staging groups: see baseline doc Gate A.

---

## 4. Database migration readiness

| Revision | Offline audit | Applied |
|----------|---------------|---------|
| `20261104_0001` | Pass | **Unknown** (not probed; do not assume) |
| `20261104_0002` | Pass | **Not applied** |
| `20261105_0003` | Pass | **Not applied** |

Order: `0001` → `0002` → `0003`. RLS select-own on bindings; no INSERT for authenticated; no broad schema GRANTs. Rollback: downgrade to `0001` after backup. Operator commands in activation runbook Gate B–C.

---

## 5. Authentication and authorization findings

- JWT path rejects `anon` / `service_role`; expired → `401 token_expired`.
- Owner-bound reads require active binding + `PRIVATE_DATA_READS` (still false → `ownership_schema_required`).
- Client-supplied binding IDs checked against owner (`cross_tenant_forbidden`).
- Operator-local diagnostics: loopback peer only; reject Authorization + X-Forwarded-For.
- Next proxy: JWT forward only; break-glass never used when Bearer present; `Cache-Control: no-store`.
- Browser: Supabase `getSession()` preferred; interim sessionStorage fallback; `signOutBrowserSession()` clears both.

---

## 6. Account binding and credential resolver

- Enrollment requires attestation + **allowlisted** `credential_ref` only.
- Rejects injection characters (`$`, `{`, etc.) and raw-looking refs.
- Pending/revoked → `exchange_binding_inactive` (not mistaken for missing/zero).
- Resolver maps fixed env var names; never `getenv(client_input)`.
- Tests use fake wallet clients only — **no live Bybit auth calls**.

---

## 7. Frontend LIVE / SAMPLE / REPLAY

- LIVE worker path requires auth headers; rejects fixture leak (`sample_leak_rejected`).
- SAMPLE remains labeled fixtures; REPLAY offline.
- Wallet: unauthorized/missing binding messaging explicitly **not** zero balance; null equity shows `—`.
- Studio timeline nested-button hydration fix retained from prior session.

---

## 8. Runtime test evidence

Offline / in-process matrix in `tests/test_phase3c_part3_runtime_readiness.py` covers: allowlist injection, pending/revoked inactive, wrong owner, forged binding id, expired JWT, service_role, missing credential material, private-reads fail-closed, SSE disabled, empty ledger unavailable, scope mismatch, owner wallet with fake client, proxy source guards, gitignore regression.

**Not runtime-verified:** migrated Postgres enrollment + live Bybit read (Gates D–G).

---

## 9. Test / build results (executed this session)

| Command | Result |
|---------|--------|
| `uv run pytest -q` | **256 passed** |
| `apps/web npm run typecheck` | **pass** |
| `apps/web npm run lint` | **pass** (SWC native warning on host) |
| `npx vitest run` | **15 passed** |
| `apps/web npm run build` | **pass** |
| Migration offline audits | **ok** for 0001/0002/0003 |

---

## 10. Remaining blockers

1. Operator Gate B: verify actual DB revision (backup + `alembic current`).
2. Operator Gate C: apply `0002` then `0003` (approval).
3. Operator Gate D: provision credentials; enroll one owner binding.
4. Operator Gate E–F: isolation on real DB; then separate approval for `PRIVATE_DATA_READS_ENABLED`.
5. Commit Phase 3B/3C tree when operator requests (include newly visible `apps/web/src/lib`).
6. Disable break-glass on any shared deploy (`OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false`).

---

## 11. Explicit operator approval checklist

- [ ] Gate A — Git/secret review  
- [ ] Gate B — Backup + revision probe  
- [ ] Gate C — Migrate 0002/0003  
- [ ] Gate D — One attested binding + credential env  
- [ ] Gate E — Isolation evidence  
- [ ] Gate F — `PRIVATE_DATA_READS_ENABLED` (separate approval)  
- [ ] Gate G — Browser LIVE verification  
- [ ] Keep SSE off; no order mutation HTTP; no auto trading  

---

## 12. Recommended next phase

**Phase 3C Part 4 / Production enablement:** execute runbook Gates B–G under change control; wire full Supabase Auth UI session lifecycle in settings; binding-scoped SSE design (still off until proven); owner-bound order/fill read contracts; commit and PR the Phase 3B/3C delta in the recommended staging groups.

---

## Success statement

Phase 3C Part 3 delivers **secure runtime readiness**: documented evidence, hardened allowlists and session handling, fixed gitignore exposure of web `lib/`, and a gated activation runbook. CryptoNova is ready for **operator-controlled** ownership-verified read-only activation — **not** automatically activated.
