# Phase 4D Gate B — Migration Execution Report

**Status: MIGRATION VERIFIED**  
**UTC start:** 2026-11-07T15:10:32Z  

## A. Executive summary

Alembic migration `20261107_0004` was applied to Supabase project `wmirifmgaftassgrfbyl` after explicit operator approval. Remote revision is **`20261107_0004`**. Five new empty `app` tables exist with RLS + SELECT-own policies. Existing tables preserved. Cloud writes, sync, import, and exchange orders remain disabled. Gate C/D/E not started.

## B. Operator approval evidence

Operator message in this conversation authorized:

- Project `wmirifmgaftassgrfbyl` for personal CryptoNova development/testing only  
- No critical production data  
- Residual Free-plan recovery risk accepted  
- SQLite backup `data/backups/multi_agent_signals_20261107_202853.sqlite3`  
- Scope limited to migration `20261107_0004` + read-only verification  

## C. Verified Supabase target

| Field | Value |
| --- | --- |
| Project ref | `wmirifmgaftassgrfbyl` |
| Host (redacted) | `aws-0-ap-southeast-2.pooler.supabase.com` |
| Identity guard | `classification=development` at apply |
| Alembic before | `20261105_0003` |
| Alembic after | `20261107_0004` |

## D. SQLite backup results

| Field | Value |
| --- | --- |
| File | `data/backups/multi_agent_signals_20261107_202853.sqlite3` |
| integrity_check | ok |
| schema_version | 4 |
| Counts | signal_history 3 · paper_risk_state 1 · checkpoints 0 · outbox 0 |

## E. Supabase backup risk status

Managed scheduled backups unavailable (Free). Residual development-only recovery risk **accepted by operator**. No cloud backup created by this process.

## F. Migration checksum

SHA-256 `1ea22dc805ff5bb235fec970cec1dd9b120c0daab573b210256d50856c722145` — verified before promote/apply. File promoted to `apps/api/alembic/versions/`.

## G. Migration execution command

```text
python -m alembic -c apps/api/alembic.ini upgrade 20261107_0004
```

Session guards: `CRYPTONOVA_DB_TARGET=development`, `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes` (restored to disabled in-process after). Exit code **0**. Transactional DDL assumed by Alembic.

## H. Alembic revision before / after

| Before | After |
| --- | --- |
| `20261105_0003` | `20261107_0004` |

## I. Created tables

All present, row counts **0**:

1. `app.signal_history`  
2. `app.signal_agent_contributions`  
3. `app.signal_risk_events`  
4. `app.scheduler_evaluation_history`  
5. `app.scheduler_audit`  

## J. Constraints and indexes (sampled)

- Uniques on `signal_history`: `uq_signal_history_decision_id`, `uq_signal_history_owner_idempotent`  
- Indexes: `ix_signal_history_owner_ts`, `ix_signal_history_owner_symbol_tf`, `ix_signal_history_owner_strategy` (+ PK/unique indexes)  
- FK: `fk_signal_contrib_signal` on contributions  

## K. RLS and security verification

| Table | RLS enabled | Policy |
| --- | --- | --- |
| signal_history | yes | `signal_history_select_own` |
| signal_agent_contributions | yes | `signal_agent_contributions_select_own` |
| signal_risk_events | yes | `signal_risk_events_select_own` |
| scheduler_evaluation_history | yes | `scheduler_evaluation_history_select_own` |
| scheduler_audit | yes | `scheduler_audit_select_own` |

Runtime RLS as end-user JWT / Data API: **NOT VERIFIED** under Gate B (no user insert/test). Privileged app role may still BYPASSRLS — application owner filters remain mandatory.

## L. Existing data preservation

Still present: `agent_decisions`, `system_events`, `strategy_configs`, `exchange_account_bindings`. New tables empty (no import).

## M. Safety gate verification

Write/sync/binding/live/order flags remained OFF throughout; not enabled by this gate.

## N. Test results

Remote catalog verification queries: **PASS**. Offline Python/frontend suites not re-run in this apply step.

## O. Remaining risks

- Free plan: no managed PITR/scheduled backups  
- Privileged `DATABASE_URL` BYPASSRLS  
- Cloud signal writes still intentionally disabled (empty cloud history until Gate C)  

## P. Recommended next phase

**Gate C** (separate approval): controlled Supabase signal-write verification with dual write gates — do not enable sync/import/orders in the same step.
