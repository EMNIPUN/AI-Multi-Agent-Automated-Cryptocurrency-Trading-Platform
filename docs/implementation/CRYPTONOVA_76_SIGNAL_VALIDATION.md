# CryptoNova 76 — Signal Validation

No signal row was inserted into the development database. The read-only catalog showed `app.signal_history` count `0` before local testing. The owner UUID is not recorded here.

## Local evidence already in the suite

| Behavior | Where it is tested |
| --- | --- |
| BUY, SELL, HOLD, BLOCKED | `tests/test_phase4a_multi_agent_signals.py` and Phase 4B history tests |
| Duplicate signal prevention | `test_duplicate_signal_suppressed`, `test_signal_persistence_and_idempotency` |
| Checkpoint and restart | `test_restart_checkpoint_recovery`, `test_restart_recovery_and_risk_halt_persistence` |
| Missing owner fails closed | `test_signal_status_without_owner_is_conflict` deletes `SIGNAL_CLOUD_OWNER_USER_ID` and expects HTTP 409 `signal_owner_unconfigured` |
| Interactive JWT must match the bound owner | `assert_principal_matches_bound_owner` and `test_jwt_cloud_history_auth` |
| Cross-user filter | `test_cross_user_access_denied_by_owner_filter` uses the application owner filter |
| PostgreSQL outbox is not a successful empty drain | Postgres dialect methods raise `outbox_not_applicable_signal_history_is_authoritative` before claim |

The gitignored environment configures `SIGNAL_CLOUD_OWNER_USER_ID`. This phase did not print it and did not change it. Unattended persistence can resolve that owner locally. A committed development write and a development process restart were not performed, because store initialization can commit a risk row when the owner is set and the source of truth is Postgres.

## Outbox boundary

SQLite remains the mirror queue. On PostgreSQL, enqueue, claim, and lease fail closed. `drain_outbox_once` returns the structured reason `outbox_not_applicable_signal_history_is_authoritative` when the backend is not SQLite. It does not report a successful queue drain. The signal row itself can still commit. `execution_allowed` stays false.

## Not claimed

Cross-user isolation was not proven through the privileged development role. That role bypasses RLS (`rolbypassrls=true` on the read-only probe). Application-layer owner filters are the current control, and they are unit-tested. Development restart recovery is unverified.
