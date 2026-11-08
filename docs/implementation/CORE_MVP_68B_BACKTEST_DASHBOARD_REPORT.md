# CryptoNova — Master Prompt 68B Backtest Dashboard Report

| Field | Value |
| --- | --- |
| Status | COMPLETE |
| Date | 2026-11-08 |
| Depends on | Prompt 68A engine + JSON reports |

---

## Implementation summary

Read-only discovery and inspection of saved 68A backtest JSON reports via FastAPI (`BACKTEST_READ_API_ENABLED`, default OFF) and Next.js `/backtesting`. No browser-triggered runs, no paper-session mixing, no fixture-as-live results.

## Architecture

```
68A persist_run_artifact → data/backtests/bt_*_report.json
        ↓
FastAPI /api/v1/backtests/* (loopback + gate)
        ↓
Next.js /api/backtests/* proxy allowlist
        ↓
/backtesting dashboard (run selector + panels)
```

## Saved result storage

- Canonical: `{run_id}_report.json` under `data/backtests/` (or `BACKTEST_RESULTS_DIR`)
- Atomic write (tmp + replace)
- Contains: config, dataset identity/hash, counters, decisions, executions, 67A analytics embed, equity curve, warnings, result_hash
- Agent traces: contribution biases + final Coordinator/Risk fields only (not full per-agent payloads)

## Signal/order reconciliation

Demo-style counts (many BUY, fewer fills, still fewer closed trades) are expected:

- Multiple BUY decisions while a position/pending order exists → reject (`SYMBOL_PENDING_ORDER` / exposure / cash)
- Cash-cap still yields rejects when lifecycle blocks new entries
- Filled orders may remain open at dataset end (not closed trades)
- UI shows rejection breakdown and decision→submit→fill join; does not equate BUY≡trade

## Files

| Path | Role |
| --- | --- |
| `agent/backtest/artifacts.py` | Atomic persist + safe load/list |
| `apps/api/app/backtests/*` | Read API |
| `apps/web/src/app/api/backtests/**` | Proxies |
| `apps/web/src/app/backtesting/*` | Dashboard |
| `apps/web/src/lib/backtest/*` | Client + tests |
| `apps/web/src/lib/security/public-backtest-proxy.ts` | Allowlist |
| Docs + roadmap | 68B DONE / 68C next |

## Tests (actual)

| Suite | Result |
| --- | --- |
| `test_core_backtest_api_68b.py` + `test_core_backtest_68a.py` | **25 passed** |
| paper analytics + broker + phase4a | **57 passed** |
| vitest `backtest-ui` + `analytics-ui` | **11 passed** |
| `tsc --noEmit` / `next lint` | **clean** |

## Safety

- Defaults OFF: `BACKTEST_READ_API_ENABLED`, existing `PAPER_*`, `AGENT_ALLOW_LIVE`, `LLM_AGENTS_ENABLED`
- GET never executes a backtest or creates results dirs
- No live exchange / OpenAI / cloud writes / Gate 63

## Known limitations

1. Full Market/Trend/Momentum narrative payloads are not in 68A reports (biases only).
2. Equity sparsity warnings inherited from 67A snapshot series.
3. No 68B POST run workflow (deferred to 68C).

## Next milestone

**Prompt 68C — Controlled historical data selection and backtest run workflow**
