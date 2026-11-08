# Phase 4C — Gate Summary

## Status: PASS (signals-only automatic closed-candle engine)

### Implemented

| Area | Status |
|------|--------|
| Persistence fail-closed (no soft-fail actionable signals) | **Done** |
| Atomic decision + paper-risk write | **Done** |
| Schema v2 checkpoints / lock / audit | **Done** |
| Closed-candle auto engine + REST backfill/poll | **Done** |
| Single-writer SQLite lease | **Done** |
| Engine status + loopback start/stop API | **Done** |
| Agent Studio engine panel | **Done** |
| Scoring model | **Unchanged** (`4B.1.0`) |

### Evidence — no real trading

- `execution_allowed=false`, `trading_enabled=false` on status/engine APIs
- Engine refuses start if `AGENT_ALLOW_LIVE` is true
- No order endpoints; public REST/WS only for market data
- Kill switches unchanged (`PRIVATE_DATA_READS_ENABLED=false`, binding persistence off)
- Operator wallet config preserved and unused by signal engine

### Startup

```powershell
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8200
cd apps\web
npm run dev
```

Optional autoload:

```text
SIGNAL_AUTO_ENGINE_ENABLED=true
SIGNAL_AUTO_SYMBOLS=BTCUSDT
SIGNAL_AUTO_INTERVAL=15
```

Or use **Start auto** on `/agents/live` (loopback only).

DB: `data/multi_agent_signals.sqlite3` (or `MULTI_AGENT_SIGNALS_DB`).

### Limitations

- Personal single-host design; lease prevents a second local writer but is not a distributed lock service
- Backfill capped at 3 candles per start
- Queue depth capped (64); overflow drops with retry via later REST poll
- WS reconnect relies on `PublicMarketWsManager`; REST poll covers missed confirms
- No outcome/PnL metrics
- Windows may need API on **8200**

### Docs

- `PHASE_4C_AUTOMATIC_SIGNAL_ARCHITECTURE.md`
- `PHASE_4C_PERSISTENCE_SAFETY.md`
- `PHASE_4C_TEST_RESULTS.md`
- this gate summary
