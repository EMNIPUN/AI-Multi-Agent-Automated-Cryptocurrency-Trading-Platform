# CryptoNova 76 — Local PostgreSQL Backtest Parity

All PostgreSQL evidence in this document is localhost `127.0.0.1:55432`. None of it is the development Supabase project.

The runner default remains SQLite. `run_backtest(..., journal_mode="postgres")` raises `backtest_postgres_runtime_not_enabled` before creating a journal file and without changing `SUPABASE_SOT_ENABLED`. A PostgreSQL failure does not fall back to SQLite. Historical `bt68a_*.sqlite3` archives were not deleted.

## Storage selection

| Mode | Behavior |
| --- | --- |
| `sqlite` (default) | Isolated SQLite paper journal. Unchanged. |
| `postgres` | Fail closed. No file. No source-of-truth mutation. |
| Export helper | Explicit caller. Copies one finished SQLite run into a PostgreSQL journal. Not used by the runner. |

## Comparisons

### BTCUSDT, 15-minute, 230 synthetic candles

`tests/test_core_75_local_journal.py` runs the same config twice on SQLite.

- Result hashes match.
- Final available balances match.
- Export fill count, fee total, and slippage total match the PostgreSQL rows.
- Replaying the export does not add fills.
- A second run id stays isolated.
- Reopening the engine still reads the first run.
- A failing PostgreSQL `begin()` leaves the SQLite available balance unchanged.
- Closed-trade `total_fees` is less than or equal to the sum of fill fees.

### ETHUSDT 5-minute and BTCUSDT 60-minute

`test_eth_and_second_timeframe_sqlite_matches_local_postgres` runs both through the SQLite runner, exports each to a disposable database named `cryptonova_76_parity`, and compares every fill as a `Decimal` tuple of price, quantity, fee, and slippage. Replay keeps the same fill count. Position quantity, when a row exists, is non-negative. Equity row count matches the export. The database is dropped afterward.

### Direct journal fixture

On the upgraded `0012` schema, two ETH-shaped partial fills share one timestamp and use sequence 1 and 2. Fees sum to `0.04` and slippage sums to `0.06`. A second `write_run` does not insert duplicates. This is a journal contract fixture, not a strategy decision.

## Difference classification

| Observation | Class |
| --- | --- |
| Closed-trade analytics fees can be lower than the sum of all fill fees. The previous BTC fixture measured closed-trade fees `40.22621097` and fill fees `50.34005213`. | Expected representation difference. Open-position entry fees are not closed-trade performance. Tests use `Decimal` `<=` and do not round the values together. |
| PostgreSQL numeric text can render scale differently from SQLite string form. | Expected representation difference. Comparisons convert both sides with `Decimal` before equality. |
| Stop-loss-before-take-profit and gap-through-stop are asserted on the SQLite execution functions in `tests/test_core_backtest_68a.py` and `tests/test_core_paper_broker.py`. | Test-fixture limitation for the PostgreSQL projection. Those rules run before export. The journal stores the resulting fills. No separate stop was fabricated for the synthetic trend. |
| Risk halt behavior is covered by signal and paper SQLite tests. The export writes the session risk row, including `halted`. | The synthetic parity runs are not required to halt. Absence of a halt in those fixtures is not an accounting mismatch. |
| Development `app.backtest_exec_runs` is absent. | Implementation is local only. Development parity is not started. |

No real accounting mismatch was observed on the localhost comparisons that completed.

## Not claimed

The backtest runtime is not on PostgreSQL. Development parity was not run. Profitability is not claimed.
