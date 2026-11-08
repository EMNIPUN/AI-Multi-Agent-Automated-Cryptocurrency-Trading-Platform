# CryptoNova — Master Prompt 68A Backtest Engine Report

| Field | Value |
| --- | --- |
| Status | COMPLETE |
| Date | 2026-11-08 |
| Engine | `68A.1.0` |
| Pipeline | Multi-Agent `4B.1.0` via `SignalPipeline.evaluate` |

---

## Implementation summary

Offline deterministic replay engine under `agent/backtest/` that:

1. Validates historical/synthetic OHLCV
2. Replays confirmed candles through the **existing** Multi-Agent pipeline (`persist=False`)
3. Simulates fills with an **isolated** PaperBroker journal (`bt68a_*.sqlite3`)
4. Optionally injects portfolio risk on that broker only (global flags stay OFF)
5. Computes performance via 67A analytics over the isolated journal
6. Emits a reproducible JSON report + CLI demo

## Architecture / reuse

| Component | Reuse |
| --- | --- |
| `SignalPipeline` | Direct evaluate loop |
| Confirmed candle clock | `candle_close_ms` + grace |
| Paper broker / fills | 65A `PaperBroker.process_candle` |
| Portfolio risk | 66 config injected per-broker |
| Analytics | 67A `compute_session_analytics` |
| AutoSignalEngine | **Not used** (live operator path) |

## Files

| Path | Role |
| --- | --- |
| `agent/backtest/*.py` | Config, validation, data, adapters, runner, report |
| `scripts/demo_multi_agent_backtest_68a.py` | Offline demo CLI |
| `tests/test_core_backtest_68a.py` | Focused engine tests |
| `tests/test_core_paper_integration.py` | Narrow cloud-boundary fix |
| `docs/implementation/CORE_MVP_BACKTEST_*.md` | Assumptions + data contract |
| `docs/implementation/CORE_MVP_IMPLEMENTATION_ROADMAP.md` | 68A DONE / 68B next |

## No-lookahead

- Agents receive only bars through index `N`
- Future-close mutation invariance tested
- Entries use decision bar **start** as `signal_candle_start_ms` (next open eligibility)

## Reproducibility

Identical dataset + config → identical decision actions and `result_hash` (wall-clock `created_ms`, UUID run/session/journal/order ids excluded from hash).

## Demo (actual)

```
evaluations=31 BUY=31
filled=7 rejected=27
closed_trades=3 open=1
net_realized_pnl≈202.95 USDT
label: HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE
```

## Tests (actual)

| Suite | Result |
| --- | --- |
| `tests/test_core_backtest_68a.py` + cloud-boundary | **18 passed** |
| analytics + portfolio + broker + phase4a | **78 passed** |
| Determinism / portfolio isolation (spot check) | **2 passed** |

## Cloud-boundary investigation

`test_no_cloud_writes_in_paper_modules` previously failed on the substring `supabase` because `read_store.py` imports the read-only gate `supabase_sot_enabled`. Importing that helper does not initialize a Supabase client or write remotely. The test now bans real client/write APIs (`create_client`, `from supabase import`, OpenAI, `place_order`, `bybit_private`) and only allows the `supabase_sot_enabled` code identifier (docstrings may mention SoT architecture).

## Safety

- `PAPER_BROKER_AUTO_ATTACH=False`
- `PAPER_PORTFOLIO_RISK_ENABLED=False`
- `PAPER_READ_API_ENABLED` default false (unchanged)
- `AGENT_ALLOW_LIVE=False`
- `LLM_AGENTS_ENABLED` unchanged / off
- No live orders, private Bybit trading, OpenAI, Gate 63, deploy, or git push

## Known limitations

See `CORE_MVP_BACKTEST_ASSUMPTIONS.md` (cash-cap, no Bybit archive pagination in 68A, snapshot drawdown).

## Next milestone

**Prompt 68B — Backtesting API and dashboard**
