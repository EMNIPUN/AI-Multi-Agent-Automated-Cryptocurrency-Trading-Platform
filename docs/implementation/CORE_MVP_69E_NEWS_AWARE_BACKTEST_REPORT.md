# CryptoNova — 69E News-Aware Backtest

## Status

Implemented and tested as a shadow layer on the existing 68A engine. Not operationally verified against development news history, because that history does not exist yet. Historical news backtesting is **not valid** on the current database.

## Integration

`run_backtest` is unchanged. `annotate_shadow` reads a completed result and attaches `extras.shadow_69e`. It does not open a second broker, does not rewrite the isolated journal, and does not call the signal pipeline again.

Modes:

- `technical_baseline`
- `news_advisory_shadow`
- `llm_advisory_shadow`

`GET /api/v1/backtests/shadow-status` reports the provenance blocker. It does not start a run and does not call a model. `/backtesting` shows **Historical Simulation — Not Live Trading** and **Advisory Only — Trading Decisions Unchanged**, and it refuses a news comparison when revision coverage is incomplete.

## Migrations

Not applied. Pending, in order: `20261108_0008`, `20261108_0009`, `20261108_0010`. Last verified development revision remains `20261108_0007` on project `wmirifmgaftassgrfbyl`.

`0010` is append-only. SQLite is rejected as the revision archive. A missing table returns storage unavailable instead of an in-memory source of truth.

## Safety

`NEWS_LLM_ENABLED` and `AGENT_ALLOW_LIVE` stay false. No live orders, no Risk override, no strategy mutation, no Telegram send, and no production migration.

The 69D spend limit is process-local. 69E does not rely on it because it does not call OpenAI.

## Tests

```
uv run pytest tests/test_core_backtest_69e.py tests/test_core_backtest_68a.py tests/test_core_backtest_api_68b.py tests/test_core_backtest_history_68c.py tests/test_core_backtest_run_api_68c.py tests/test_core_news_69a.py tests/test_core_news_69a1.py tests/test_core_news_69b.py tests/test_core_news_69c.py tests/test_core_llm_69d.py -q
→ 94 passed, 1 skipped, 0 failed
```

The skip is the optional live Postgres news integration. Web unit tests for backtest, LLM, and news labels: 11 passed. The signed-in `/backtesting` page was not opened in a browser.
