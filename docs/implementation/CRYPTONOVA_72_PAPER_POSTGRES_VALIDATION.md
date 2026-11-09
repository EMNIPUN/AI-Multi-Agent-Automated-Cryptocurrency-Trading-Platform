# CryptoNova 72 — Paper PostgreSQL Validation

Read-only catalog on development revision `20261108_0011`. No paper row was inserted, updated, or deleted. SQLite journals were not removed.

| Table | Count |
| --- | --- |
| paper_sessions | 3 |
| paper_session distinct owners | 1 |
| paper session status ACTIVE | 3 |
| paper_account_events SESSION_CREATED | 3 |
| paper_orders | 0 |
| paper_fills | 0 |
| paper_positions | 0 |
| paper_equity_snapshots | 0 |

`GET /api/v1/paper/status` returned 200 with `paper_read_api_enabled` false and `execution_allowed` false. The disabled status path does not open the database. The enabled path remains loopback-only. The flag was not turned on.

Owner isolation is present on `paper_sessions.owner_user_id` (not null) and RLS is enabled. The current API role bypasses RLS, so the database policy is not the live enforcement path.

Fill, fee, realized PnL, unrealized PnL, and risk-halt behavior were not replayed on these three sessions because they contain no orders. Existing SQLite fixture tests still cover that accounting. Isolated backtest journals do not write those sessions.

Analytics over PostgreSQL paper rows is not verified. There are no fills to aggregate.
