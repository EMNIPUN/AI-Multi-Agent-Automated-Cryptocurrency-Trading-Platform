# Phase 3C Part 3 — Operator Activation Runbook

**DO NOT auto-execute Gates C–F.** Explicit operator approval required per gate.
This runbook never flips `PRIVATE_DATA_READS_ENABLED` or enables SSE/trading.

Companion baseline: `PHASE_3C_PART3_SECURITY_BASELINE.md`

---

## GATE A — Git / secret safety

### Prerequisites
- Working tree inspected; no accidental secrets staged
- `.gitignore` uses `/lib/` (not bare `lib/`) so `apps/web/src/lib` is trackable
- `apps/web/.env.local` remains ignored

### Commands (read-only)
```bash
git status -sb
git check-ignore -v apps/web/.env.local apps/web/src/lib/auth/browser-access-token.ts
git diff --stat
# Secret scan without printing values:
git grep -I -n -E "BYBIT_API_SECRET|DATABASE_URL=|service_role" -- ':!.env.example' || true
```

### Expected
- `.env.local` ignored
- `browser-access-token.ts` **not** ignored
- No real secrets in tracked content

### Failure / STOP
- If secrets appear in tracked files → STOP, scrub, rotate keys
- Do not `git add -f` env files

### Evidence checklist
- [ ] Status reviewed
- [ ] Ignore rules verified
- [ ] Staging groups planned (no auto-commit)

---

## GATE B — Database backup & revision probe

### Prerequisites
- Supabase/Postgres backup or PITR available
- Server-side `DATABASE_URL` available to operator (not committed)

### Commands (read-only preferred)
```bash
# Offline migration audit (safe)
uv run python -c "from apps.api.app.migration_audit import audit_initial_migration, audit_ownership_migration, audit_exchange_binding_migration as a3; print(audit_initial_migration()); print(audit_ownership_migration()); print(a3())"

# If DATABASE_URL set — query current revision ONLY (read-only role preferred)
cd apps/api
alembic current
# Optional schema probe (read-only SQL):
# SELECT version_num FROM app.alembic_version;
# SELECT tablename FROM pg_tables WHERE schemaname='app';
```

### Expected
- Offline audits `ok=True`
- Current revision known (do **not** assume `0001` from file presence)
- `app` schema not exposed in Supabase Data API

### Failure / STOP
- Unknown revision / schema drift → STOP before upgrade
- Backup missing → STOP

### Evidence checklist
- [ ] Backup confirmed
- [ ] `alembic current` recorded
- [ ] Review SQL read: `apps/api/sql/review/20261104_0002_*.sql`, `...20261105_0003_*.sql`

---

## GATE C — Apply migrations (approval required)

### Prerequisites
Gate B complete + written approval

### Commands
```bash
cd apps/api
# Backup first
alembic upgrade 20261104_0002
alembic upgrade 20261105_0003
alembic current
```

### Rollback (after backup only)
```bash
alembic downgrade 20261104_0001
```

### Expected
- `0003` head
- `app.exchange_account_bindings` exists
- RLS enabled; no broad GRANTs to anon

### Failure / STOP
- Upgrade error → stop; restore from backup; do not stamp
- Do not set `PRIVATE_DATA_READS_ENABLED`

### Evidence checklist
- [ ] Approval recorded
- [ ] Upgrade output saved
- [ ] `alembic current` = `20261105_0003`

---

## GATE D — Credential refs + one owner binding (approval required)

### Prerequisites
Gate C complete; allowlisted env secrets provisioned server-side

| credential_ref | Env vars | Environment |
|----------------|----------|-------------|
| `env:BYBIT_TESTNET_OPERATOR` | `BYBIT_TESTNET_API_KEY/SECRET` | testnet |
| `env:BYBIT_MAINNET_OPERATOR` | `BYBIT_MAINNET_API_KEY/SECRET` | mainnet |
| `env:BYBIT_DEMO_OPERATOR` | `BYBIT_DEMO_API_KEY/SECRET` | demo |
| `env:BYBIT_OPERATOR` | `BYBIT_API_KEY/SECRET` + flags | derived |

### Enrollment rules
- Exactly **one** verified Supabase user UUID
- Attestation required
- Prefer `pending` then activate after review
- Never auto-assign operator account to all users
- Set worker: `EXCHANGE_ACCOUNT_BINDING_ID=<binding-uuid>`

### Failure / STOP
- Ambiguous multi-owner binding → STOP
- Unknown credential_ref → STOP

### Evidence checklist
- [ ] Binding row active for intended owner only
- [ ] Telemetry scope = binding id
- [ ] Secrets never stored in table

---

## GATE E — Isolation verification (read-only)

### Prerequisites
Gates C–D; still **keep** `PRIVATE_DATA_READS_ENABLED=false` for negative tests first

### Commands (examples)
```bash
uv run pytest -q tests/test_phase3c_part3_runtime_readiness.py tests/test_exchange_bindings_phase3c.py tests/test_exchange_bindings_phase3c_part2.py
# With flag false: owner path must 403 ownership_schema_required
# After Gate F only: positive owner wallet/telemetry against migrated DB
```

### Expected
- Wrong owner / revoked / pending / wrong env denied
- No secrets in responses
- Scope mismatch → unavailable snapshot (not SAMPLE)

### Failure / STOP
- Cross-user leak → STOP; leave private reads off

---

## GATE F — Private reads flag (separate explicit approval)

### Prerequisites
Gates A–E all green

### Command (operator-controlled env only)
```bash
# ONLY after written approval — not done by automation
PRIVATE_DATA_READS_ENABLED=true
# Keep:
OBSERVABILITY_LIVE_STREAM_ENABLED=false
OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false   # multi-user / hosted
```

### Rollback
```bash
PRIVATE_DATA_READS_ENABLED=false
```

### STOP conditions
- Any isolation failure → immediate rollback of flag

---

## GATE G — Browser LIVE verification

### Prerequisites
Gate F approved (or local break-glass for single-operator only)

### Checks
- LIVE uses Bearer from Supabase session (or interim token)
- SAMPLE labeled; LIVE never falls back to SAMPLE
- Unauthorized / missing binding ≠ zero balance
- Stale heartbeat ≠ fabricated RUNNING HOLD
- Break-glass disabled on shared hosts

### Evidence checklist
- [ ] Owner wallet 200 (post Gate F)
- [ ] Wrong user 403
- [ ] Worker snapshot scoped
- [ ] SSE still 403

---

## Global STOP rules

1. No real Bybit orders / cancel / leverage / transfers  
2. No SSE enable  
3. No automatic `PRIVATE_DATA_READS` flip  
4. No remote migration without Gate C approval  
5. No commit/push without explicit ask  
6. Never print secrets  
