# CryptoNova 76 — Migration 0012 Readiness

Migration file: `apps/api/alembic/versions/20261108_0012_backtest_exec_journal_72.py`

This revision is **not approved** and was **not applied** to the development project `wmirifmgaftassgrfbyl`.

## Checksum

SHA-256 of the current file:

`79d1197e675da8dd8dc057670af762a23e385ddcb1bcaf26db6b66c0a4cb11d5`

The Phase 75 revised report recorded the same digest. The file was not edited in Phase 76, so the previous checksum remains valid. `tests/test_core_76_local_migration.py::test_migration_0012_checksum_is_unchanged` asserts this value.

## What the revision defines

Six tables in schema `app`:

- `backtest_exec_runs`
- `backtest_exec_orders`
- `backtest_exec_fills`
- `backtest_exec_positions`
- `backtest_exec_equity`
- `backtest_exec_risk`

| Control | Revision behavior |
| --- | --- |
| Owner | `owner_user_id` is `NOT NULL` on every table. |
| Run isolation | `run_id` is the run primary key. Child rows reference it with `ON DELETE CASCADE`. |
| Order idempotency | Unique `(run_id, idempotency_key)` named `uq_backtest_exec_orders_idem`. |
| Fill sequence | Unique `(run_id, order_id, fill_seq)` named `uq_backtest_exec_fills_seq`. Check `fill_seq >= 1`. |
| Same-millisecond partials | Uniqueness is the sequence, not the timestamp. Two fills may share `filled_at_ms`. |
| Deterministic fill IDs | The journal writer hashes `run_id\|order_id\|fill_seq`. A mismatched supplied id is rejected. The migration stores that id as the fill primary key. |
| Slippage | `numeric(28,12) NOT NULL` on fills. |
| Fees | `numeric(28,12) NOT NULL` on fills. |
| Positions | Unique `(run_id, symbol)`. Quantity and average price are `numeric(28,12)`. |
| Equity | `equity` and `cash` are `numeric(28,12)`, indexed by run. |
| Risk | One risk row per run, with `halted` and `reason`. |
| Indexes | `ix_backtest_exec_orders_run`, `ix_backtest_exec_fills_run`, `ix_backtest_exec_fills_order_seq`, `ix_backtest_exec_equity_run`. |
| RLS | `ENABLE` and `FORCE` on all six tables. Policies `select_own`, `insert_own`, and `update_own` for role `authenticated` compare `owner_user_id` to `auth.uid()`. No DELETE policy. No GRANT. |
| Downgrade | Drops update, insert, then select policies, then drops tables from risk back to runs. |

Transaction atomicity belongs to `PostgresBacktestJournal.write_run`, which writes the run, orders, fills, positions, equity, and risk in one transaction. A failed begin leaves the SQLite journal unchanged. That behavior is covered by `tests/test_core_75_local_journal.py`.

## Local proof

`test_migration_0012_upgrade_and_downgrade_on_localhost` loads the revision module and calls `upgrade()` and `downgrade()` through Alembic `Operations` on a disposable database at `127.0.0.1:55432`. It does not call Alembic `env.py` and does not use the development URL.

The upgrade test observed:

- all six tables present
- `backtest_exec_fills` has row security enabled and forced
- `slippage` is `numeric(28,12)`
- two partial fills at the same millisecond, sequence 1 and 2, survive a second identical `write_run`
- fee total `0.04` and slippage total `0.06` with no rounding
- `to_regclass('app.backtest_exec_runs')` is null after downgrade
- the disposable database is dropped

The local cluster role `authenticated` and function `auth.uid()` exist only inside that disposable database. They were not created on the development project.

## Checklist

- [x] Checksum recomputed and unchanged
- [x] Upgrade succeeds on disposable localhost PostgreSQL
- [x] Downgrade removes the journal tables
- [x] Same-millisecond partial fills persist on the upgraded schema
- [x] Replay does not add fills
- [ ] Operator approval for development apply
- [ ] Fresh recoverable backup of the development project
- [ ] Apply on `wmirifmgaftassgrfbyl`

The last three items are future work. This document does not approve them.
