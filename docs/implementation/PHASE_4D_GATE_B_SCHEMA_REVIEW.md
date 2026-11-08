# Phase 4D Gate B — Schema / Migration Review

**Proposed file:** `apps/api/alembic/versions_proposed/20261107_0004_phase4d_signal_persistence.py`  
**Revision:** `20261107_0004`  
**down_revision:** `20261105_0003`  
**Moved to active versions:** **no** (this preparation does not move it)  
**Applied:** **no**

## Active chain (repository)

```text
20261104_0001 → 20261104_0002 → 20261105_0003 (HEAD)
proposed:        20261107_0004 (parents HEAD; not discoverable)
```

Static check (`scripts/_static_alembic_4d_check.py`): `down_matches_active_head=True`, `discoverable_by_default_alembic=False`, `table_name_conflicts_with_active=[]`.

## Dependency graph (repository evidence)

```text
Existing (0001–0003):
  app.agent_decisions
  app.system_events
  app.strategy_configs
  app.exchange_account_bindings
  (+ ownership RLS policies from 0002/0003)

Proposed 0004 (additive only — no ALTER on existing tables):
  app.signal_history
       ↑ FK CASCADE
  app.signal_agent_contributions
       ↑ FK SET NULL
  app.signal_risk_events
  app.scheduler_evaluation_history  (no FK to signal_history)
  app.scheduler_audit               (no FK to signal_history)
```

## Collision analysis (repo-only)

| Kind | Result |
| --- | --- |
| Table names | No collision with active migrations |
| Index names (`ix_signal_*`, `ix_sched_*`) | Distinct from existing `ix_agent_*` / binding indexes |
| Constraint / policy names | Distinct (`uq_signal_*`, `*_select_own` for new tables) |
| Extensions | Uses built-in UUID/JSONB; no new extension CREATE in 0004 |
| Ordering | Parent tables before FK children |

**Remote schema compatibility:** **NOT VERIFIED** (no live catalog read).

## DDL review summary

| Item | Status |
| --- | --- |
| Schema `app` | Correct |
| UUID / BIGINT / TIMESTAMPTZ / JSONB | Correct |
| UNIQUE decision_id; owner+idempotent_key | Present |
| CHECK category/action | Present on signal_history (+ category on sched eval) |
| FK ordering | Correct |
| RLS ENABLE + SELECT-own TO `authenticated` | Present; **no INSERT/UPDATE/DELETE** policies |
| GRANTs to anon/authenticated | **None** in migration (good) |
| Unexpected ALTER of existing tables | **None** |
| Downgrade | DROP POLICY then DROP TABLE — **destructive** if populated |

## ORM alignment (`cloud_models.py`)

UniqueConstraints aligned with DDL names. CHECK constraints exist in DDL only (acceptable; DDL is SoT on apply).

## Alembic transaction behavior

`env.py` online path:

1. Connect  
2. `CREATE SCHEMA IF NOT EXISTS app` + **commit** (outside migration TX)  
3. `begin_transaction()` → `run_migrations()`  

PostgreSQL generally supports transactional DDL; some catalog ops may still behave specially. Operators should treat a failed mid-revision as “inspect `app.alembic_version` + `\d app.*` before retry,” not blind re-run.

## Code corrections this session

**None.** Proposed migration left unchanged under `versions_proposed/`.
