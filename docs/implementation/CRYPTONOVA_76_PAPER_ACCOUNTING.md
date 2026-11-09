# CryptoNova 76 — Paper Accounting

Development paper catalog, read in one read-only transaction before this phase's local work:

- 3 sessions
- 1 distinct owner
- 0 orders
- 0 fills
- 0 positions
- 0 equity snapshots

Those sessions were not updated. No fourth session was created. No development paper write was issued.

## SQLite accounting that the suite already exercises

| Behavior | Test |
| --- | --- |
| Session creation | `test_session_initialization` |
| Partial fills and duplicate fill prevention | `test_duplicate_fill` |
| Fees and adverse slippage | `test_adverse_slippage_and_entry_fee` |
| Position open and close | `test_entry_fill_opens_position`, `test_sell_closes_long_does_not_short` |
| Stop-loss before take-profit | `test_same_bar_sl_tp_collision`, `test_same_candle_sl_before_tp` |
| Take-profit and stop-loss exits | `test_tp_exit`, `test_sl_exit` |
| Realized PnL | `test_net_realized_pnl_and_balance` |
| Unrealized PnL | `test_mark_to_market` |
| Equity snapshot | `test_approved_entry_opens_and_equity_snapshot` |
| Daily loss halt and restart | `test_daily_loss_halt_and_restart` |
| Maximum drawdown halt | `test_drawdown_halt_via_equity_update` |
| Restart recovery | `test_restart_recovery` |
| Idempotent reprocessing | `test_duplicate_signal`, `test_duplicate_exit` |

These tests use disposable SQLite files. They do not open the development database.

## PostgreSQL paper path

`PaperStore` has no engine injection. `bootstrap_agent_schema` returns immediately for a non-SQLite dialect, so paper tables are not created by the application on PostgreSQL. Alembic `env.py` refuses any target that is not the development project and refuses localhost. Phase 76 did not weaken that guard and did not point paper storage at `DATABASE_URL`.

PostgreSQL paper accounting is therefore **not started** as a runtime. The SQLite accounting tests remain the verified evidence. Development paper fills stay unverified because the three existing sessions have no fills, and creating fills there is outside this phase.

The paper read API stays disabled. Disabled routes do not open the database.
