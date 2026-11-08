# Phase 3C Part 5B — Transactional RLS Execution Plan

| Field | Value |
|-------|-------|
| Status | **READY FOR APPROVAL — NOT EXECUTED** (Part 5C schema-validated) |
| Runner | `scripts/run_transactional_rls_isolation.py` (dry-run default) |
| Schema fix | `agent_decisions.strategy_id` is NOT NULL without DB default — INSERT must supply it |
| Target | Development `wmirifmgaftassgrfbyl` @ session pooler |
| Alembic | `20261105_0003` |
| Design | Single PostgreSQL transaction → **ROLLBACK** |
| Persistent GRANT/REVOKE | **Avoided** (transactional only) |

This supersedes the persistent GRANT/DELETE approach in Part 5’s earlier draft.  
See also updated `PHASE_3C_PART5_RLS_TEST_PLAN.md`.

---

## 1. Feasibility in this environment

| Factor | Evidence |
|--------|----------|
| Server | PostgreSQL **17.11** (Supabase) |
| Pooler | Session pooler (`:5432`) — suitable for `SET LOCAL ROLE` in one connection |
| `GRANT`/`REVOKE` | Transactional in PostgreSQL — rolled back with the transaction |
| Inserts | Rolled back with the transaction |
| `auth.uid()` | Reads `request.jwt.claim.sub` **or** `request.jwt.claims` JSON `sub` |
| Role `authenticated` | Exists; currently no persistent `app` USAGE/SELECT |

**Conclusion:** Class C RLS proof can be contained in one explicit transaction with `ROLLBACK`, then a **post-rollback** read-only verification that no rows/grants persist.

**Prerequisite:** Data API must confirm `app` is **not** exposed before approving even transactional GRANTs (short-lived within the TX, but still visible to concurrent sessions until commit/rollback — prefer exclusive operator window).

---

## 2. What this proves / does not prove

| Proves | Does **not** prove |
|--------|---------------------|
| SELECT-own policies filter rows for role `authenticated` under synthetic JWT GUCs | Browser Auth / JWKS cryptographic sessions |
| Pending/revoked bindings hidden by bindings policy | FastAPI ownership (Class B — already offline-tested) |
| Missing/invalid `sub` yields no owned rows | Production least-privilege app role |

---

## 3. Synthetic identities & markers

| Alias | UUID |
|-------|------|
| User A | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1` |
| User B | `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2` |
| Invalid sub | `cccccccc-cccc-4ccc-8ccc-ccccccccccc3` |

Marker string: `phase3c_part5b_rls_synth` (reason / message / enrollment_attestation / strategy name prefix).

---

## 4. Tables & minimum grants (named tables only)

Inside the transaction only:

```sql
GRANT USAGE ON SCHEMA app TO authenticated;
GRANT SELECT ON
  app.agent_decisions,
  app.system_events,
  app.strategy_configs,
  app.exchange_account_bindings
TO authenticated;
```

**Do not** use `GRANT SELECT ON ALL TABLES IN SCHEMA app`.

No INSERT/UPDATE/DELETE grants to `authenticated`.

---

## 5. Exact SQL (draft — do not run until approved)

Identity guard (PowerShell) before connecting:

```powershell
$env:CRYPTONOVA_DB_TARGET="development"
$env:CRYPTONOVA_DEV_PROJECT_REF="wmirifmgaftassgrfbyl"
$env:CRYPTONOVA_USE_DATABASE_URL_AS_DEV="true"
# CRYPTONOVA_ALLOW_DEV_MIGRATIONS must remain false
```

### 5.1 Single transaction body

```sql
BEGIN;

-- 0) Precondition snapshots (privileged)
SELECT current_user, current_setting('transaction_read_only', true);
SELECT version_num FROM app.alembic_version; -- expect 20261105_0003

-- 1) Synthetic rows (as postgres; BYPASSRLS)
INSERT INTO app.agent_decisions (
  id, owner_user_id, env_scope, account_fp, symbol, category, action, strategy_id, reason
) VALUES
  ('a1111111-1111-4111-8111-111111111111', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
   'dev', '', 'BTCUSDT', 'linear', 'hold', '', 'phase3c_part5b_rls_synth_a'),
  ('b1111111-1111-4111-8111-111111111111', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2',
   'dev', '', 'ETHUSDT', 'linear', 'hold', '', 'phase3c_part5b_rls_synth_b');

INSERT INTO app.system_events (
  id, owner_user_id, env_scope, severity, event_type, message
) VALUES
  ('a2222222-2222-4222-8222-222222222222', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
   'dev', 'info', 'rls_probe', 'phase3c_part5b_rls_synth_a'),
  ('b2222222-2222-4222-8222-222222222222', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2',
   'dev', 'info', 'rls_probe', 'phase3c_part5b_rls_synth_b');

INSERT INTO app.strategy_configs (
  id, owner_user_id, name, version, enabled, config_json
) VALUES
  ('a3333333-3333-4333-8333-333333333333', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
   'phase3c_part5b_rls_synth_a', '1', false, '{}'::jsonb),
  ('b3333333-3333-4333-8333-333333333333', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2',
   'phase3c_part5b_rls_synth_b', '1', false, '{}'::jsonb);

INSERT INTO app.exchange_account_bindings (
  id, owner_user_id, provider, environment, status, display_label,
  credential_ref, telemetry_scope_id, enrollment_attestation, enrolled_by_operator
) VALUES
  ('a4444444-4444-4444-8444-444444444441', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
   'bybit', 'testnet', 'active', 'synth-a-active',
   'env:BYBIT_TESTNET_OPERATOR', 'a4444444-4444-4444-8444-444444444441',
   'phase3c_part5b_rls_synth_a_active', true),
  ('b4444444-4444-4444-8444-444444444442', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2',
   'bybit', 'testnet', 'active', 'synth-b-active',
   'env:BYBIT_OPERATOR', 'b4444444-4444-4444-8444-444444444442',
   'phase3c_part5b_rls_synth_b_active', true),
  ('a4444444-4444-4444-8444-444444444443', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
   'bybit', 'demo', 'pending', 'synth-a-pending',
   'env:BYBIT_DEMO_OPERATOR', 'a4444444-4444-4444-8444-444444444443',
   'phase3c_part5b_rls_synth_a_pending', true),
  ('a4444444-4444-4444-8444-444444444444', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
   'bybit', 'mainnet', 'revoked', 'synth-a-revoked',
   'env:BYBIT_MAINNET_OPERATOR', 'a4444444-4444-4444-8444-444444444444',
   'phase3c_part5b_rls_synth_a_revoked', true);

-- 2) Minimum transactional grants
GRANT USAGE ON SCHEMA app TO authenticated;
GRANT SELECT ON
  app.agent_decisions,
  app.system_events,
  app.strategy_configs,
  app.exchange_account_bindings
TO authenticated;

-- 3) User A assertions
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claim.sub', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1', true);
SELECT set_config('request.jwt.claim.role', 'authenticated', true);
-- Expect: agent_decisions=1, system_events=1, strategy_configs=1, bindings=1 (active only)
SELECT 'A_agent' AS k, count(*) FROM app.agent_decisions;
SELECT 'A_events' AS k, count(*) FROM app.system_events;
SELECT 'A_strat' AS k, count(*) FROM app.strategy_configs;
SELECT 'A_bind' AS k, count(*) FROM app.exchange_account_bindings;
SELECT 'A_bind_ids' AS k, id::text, status FROM app.exchange_account_bindings;

-- 4) User B assertions
SELECT set_config('request.jwt.claim.sub', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2', true);
SELECT 'B_agent' AS k, count(*) FROM app.agent_decisions;
SELECT 'B_bind' AS k, count(*) FROM app.exchange_account_bindings;

-- 5) Missing subject
SELECT set_config('request.jwt.claim.sub', '', true);
SELECT 'MISS_agent' AS k, count(*) FROM app.agent_decisions;

-- 6) Invalid subject
SELECT set_config('request.jwt.claim.sub', 'cccccccc-cccc-4ccc-8ccc-ccccccccccc3', true);
SELECT 'INV_agent' AS k, count(*) FROM app.agent_decisions;
SELECT 'INV_bind' AS k, count(*) FROM app.exchange_account_bindings;

-- 7) Restore privileged role (still inside TX)
RESET ROLE;

-- 8) Abort everything (rows + grants)
ROLLBACK;
```

### 5.2 Mandatory post-rollback verification (new connection, READ ONLY)

```sql
BEGIN;
SET TRANSACTION READ ONLY;
SELECT count(*) FROM app.agent_decisions WHERE reason LIKE 'phase3c_part5b_rls_synth%'; -- 0
SELECT count(*) FROM app.system_events WHERE message LIKE 'phase3c_part5b_rls_synth%'; -- 0
SELECT count(*) FROM app.strategy_configs WHERE name LIKE 'phase3c_part5b_rls_synth%'; -- 0
SELECT count(*) FROM app.exchange_account_bindings
 WHERE enrollment_attestation LIKE 'phase3c_part5b_rls_synth%'; -- 0
SELECT has_schema_privilege('authenticated', 'app', 'USAGE'); -- false
SELECT has_table_privilege('authenticated', 'app.agent_decisions', 'SELECT'); -- false
SELECT has_table_privilege('authenticated', 'app.exchange_account_bindings', 'SELECT'); -- false
COMMIT;
```

If any post-rollback count/privilege is non-zero → **FAIL** and stop; escalate for manual cleanup approval.

---

## 6. Expected assertion matrix

| Step | Expect |
|------|--------|
| User A counts | 1 / 1 / 1 / **1** binding |
| User A binding statuses visible | `active` only |
| User B agent / binding | 1 / 1 (own only) |
| Missing sub | 0 agents |
| Invalid sub | 0 agents / 0 bindings |
| Post-ROLLBACK | 0 synth rows; `authenticated` USAGE/SELECT false |

---

## 7. Residual risks

| Risk | Notes |
|------|-------|
| Concurrent sessions during TX | Transactional GRANTs are visible to other sessions until ROLLBACK on PG — run in a quiet window; Data API must not expose `app` |
| Connection drop mid-TX | Server should abort uncommitted TX; still run post-verify |
| Session pooler quirks | Use **one** connection for the whole TX; avoid transaction-mode pooler (`:6543`) |
| No backup | Accepted for empty development DB; ROLLBACK verification mandatory |
| False confidence | Does not replace Class D Auth E2E |

---

## 8. STOP — operator approval request

Approve execution of **this transactional plan only** by confirming:

1. Target identity: development project **`wmirifmgaftassgrfbyl`**, revision `20261105_0003`
2. Data API: **`app` not exposed** (see `PHASE_3C_PART5B_DATA_API_VERIFICATION.md`)
3. Exact tables: the four `app.*` tables named above
4. Exact SQL: §5 (single `BEGIN` … `ROLLBACK` + post-verify)
5. No Auth users, no migrations, no PRIVATE_DATA_READS, no Bybit orders, no git commit
6. Acceptance of residual concurrent-GRANT visibility until ROLLBACK

Reply: `APPROVE_TRANSACTIONAL_RLS_PART5B` and `DATA_API_VERIFIED: app not exposed`
(or request modifications).

Execution command (only after both replies):

```powershell
$env:CRYPTONOVA_DB_TARGET="development"
$env:CRYPTONOVA_DEV_PROJECT_REF="wmirifmgaftassgrfbyl"
$env:CRYPTONOVA_USE_DATABASE_URL_AS_DEV="true"
$env:CRYPTONOVA_DATA_API_APP_NOT_EXPOSED="yes"
$env:CRYPTONOVA_APPROVE_TRANSACTIONAL_RLS="yes"
python scripts/run_transactional_rls_isolation.py --execute
```

Dry-run (safe now):

```powershell
python scripts/run_transactional_rls_isolation.py
```

**Do not execute `--execute` until both approval replies.**
