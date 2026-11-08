# CryptoNova — SQLite → Supabase SoT Cutover Runbook

| Field | Value |
| --- | --- |
| Authorization | Operator chose **everything** off SQLite + **live Supabase writes** as SoT |
| Date | 2026-11-08 |
| Alembic | Dev project applied through **`20261108_0006`** |
| Live trading | Still OFF (`AGENT_ALLOW_LIVE=false`; no Bybit private order submit) |

---

## Prerequisites

1. `DATABASE_URL` set to Supabase Postgres (service/privileged URL for FastAPI).
2. Alembic through `20261108_0005` already applied (signal mirror tables exist).
3. Apply new revision `20261108_0006_supabase_sot_cutover` before enabling app SoT writers.
4. Set owner binding:

```text
SIGNAL_CLOUD_OWNER_USER_ID=<verified Supabase Auth user UUID>
SIGNAL_SUPABASE_WRITES_ENABLED=true
SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED=true
SUPABASE_SOT_ENABLED=true
```

5. Keep OFF:

```text
AGENT_ALLOW_LIVE=false
PAPER_BROKER_AUTO_ATTACH=false
PAPER_PORTFOLIO_RISK_ENABLED=false
EXCHANGE order / binding write gates as previously fail-closed unless separately approved
```

6. Backup any local SQLite files under `data/` before import scripts run.

---

## Cutover sequence

1. Backup SQLite files (`multi_agent_signals`, `cryptonova_paper`, intents, risk, ledger, exec, observability).
2. `alembic upgrade head` (includes paper + ledger tables) — **dev applied to `20261108_0006`**.
3. Optional import scripts (dry-run default).
4. Set SoT env flags; restart API (`SUPABASE_SOT_ENABLED=true`, owner UUID, optional write dual-gates).
5. Verify Studio history + paper session GETs hit Postgres (no new `data/*.sqlite3` under SoT).
6. Agent store modules no longer import `sqlite3` (SQLAlchemy Postgres SoT; offline tests may use SQLAlchemy SQLite engines with `SUPABASE_SOT_ENABLED=false`).

## Verification (2026-11-08)

- Alembic revision on approved dev project: `20261108_0006`
- Paper + signal PG smoke scripts: OK
- Core pytest (offline `SUPABASE_SOT_ENABLED=false`): **130 passed**
- Live trading / Bybit private orders: still OFF

## Rollback (pre Phase-4 code delete)

- Revert the SoT deploy commit and restore SQLite backups.
- After SQLite code removal, rollback = git revert of the cutover commit(s), not an env flag.

## RLS note

New `app.*` tables enable RLS with `authenticated` SELECT-own policies (Option A pattern). FastAPI uses privileged `DATABASE_URL` and **must** filter by `owner_user_id` in application code.
