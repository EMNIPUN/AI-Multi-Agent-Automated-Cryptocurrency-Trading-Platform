# CryptoNova — Core MVP 68C Backtest Runner Report

| Field | Value |
| --- | --- |
| Status | **COMPLETE** |
| Engine | 68A.1.0 (reused) |
| Pipeline | 4B.1.0 (reused) |
| Read API | 68B (reused) |
| Run gate | `BACKTEST_RUN_API_ENABLED` default **false** |

---

## Executive summary

68C adds a **controlled** historical backtest workflow: public Bybit candle pagination + content-addressed cache, a gated POST run API with job lifecycle and resource limits, and a `/backtesting` **Run Historical Backtest** panel. Existing Multi-Agent Pipeline, paper simulation, risk, analytics, and 68B artifact formats are reused. No live orders, LLM calls, or cloud writes.

## Architecture

```
UI Run panel → Next same-origin POST proxy → FastAPI POST /runs
    → job queue (1 worker) → history fetch/cache → run_backtest(68A)
    → persist_run_artifact(68B) → UI polls job → opens saved run
```

## Historical market-data provider

- Module: `agent/backtest/history_provider.py`
- Public REST only; instrument verification; pagination; dedupe; conflict reject; confirmed-bar grace; timeouts/retries.
- Linear data labeled as **not** a Futures leverage backtest.

## Dataset cache

- `data/backtests/datasets/{sha256}.json` under results root
- Atomic writes; hash revalidation; identity checks; size budget

## Controlled run API

- See `CORE_MVP_BACKTEST_RUN_API_CONTRACT.md`
- Lifecycle: `QUEUED → RUNNING → COMPLETED | FAILED` (+ `INTERRUPTED` on restart)
- Idempotency keys; concurrency/queue/runtime/candle caps

## UI

- `RunBacktestPanel` on `/backtesting`
- Run button disabled when gate OFF; no auto-start; duplicate-click idempotency; genuine phase display only
- Saved-run viewer (68B) preserved

## Demonstration (offline fixture — deterministic)

| Field | Value |
| --- | --- |
| Run id | `bt_fb66b5d0eba84eed` |
| Dataset hash | `61fb4dbb542001ef5751b165b4d174d303fdf374eb5602fe104d3f6daf301522` |
| Result hash | `fd23a14e2fd53dcb72978040472f08cd31321114c3244f2b117a8bdcca757859` |
| Eligible evals | 31 |
| BUY / submitted / filled / rejected | 31 / 31 / 7 / 27 |
| Closed trades / open | 3 / 1 |
| Net realized PnL | 20.29544189 USDT (**simulation only**) |
| Label | HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE |

BUY signals ≠ filled orders ≠ closed trades (rejection evidence preserved).

## Tests

| Suite | Result |
| --- | --- |
| `test_core_backtest_68a.py` + `test_core_backtest_api_68b.py` + `test_core_backtest_history_68c.py` + `test_core_backtest_run_api_68c.py` | **41 passed** |
| `apps/web/.../backtest-ui.test.ts` | **5 passed** |

## Safety confirmation

| Flag / behavior | Status |
| --- | --- |
| `BACKTEST_RUN_API_ENABLED` | default false |
| `BACKTEST_READ_API_ENABLED` | default false (unchanged) |
| `PAPER_*` / `AGENT_ALLOW_LIVE` / `LLM_AGENTS_ENABLED` | not flipped by runs |
| Live exchange orders | none |
| Private Bybit | none |
| Cloud / Supabase writes from backtest path | none |
| OpenAI | none |

## Known limitations

- UI symbol set limited to BTC/ETH/SOL; intervals 15m/1h/4h.
- Cancellation not implemented.
- Linear market data ≠ Futures leverage simulation.
- Public Bybit rate limits / availability can fail live fetches (offline fixture path remains).
- Single-process worker thread (local operator model).

## Next recommended milestone

**News Intelligence Agent** (proposed). OpenAI explanation integration later. Gate 63 / live execution remain deferred/disabled.
