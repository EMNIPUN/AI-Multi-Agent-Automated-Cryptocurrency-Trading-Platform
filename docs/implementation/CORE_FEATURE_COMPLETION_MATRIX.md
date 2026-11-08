# CryptoNova — Core Feature Completion Matrix

| Field | Value |
| --- | --- |
| Audit date | 2026-11-08 |
| Evidence | Code + docs + safe local pytest (see audit) |
| Status legend | COMPLETE · FUNCTIONAL · PARTIAL · DESIGN ONLY · MISSING · NOT VERIFIED · BLOCKED |

---

| Module | Feature | Implementation | Tests | Integration | Status | Priority |
| --- | --- | --- | --- | --- | --- | --- |
| Market Data | Bybit public REST (klines/tickers/OB/trades) | `apps/api/app/market_data/rest_client.py` | `test_phase3d_market_data.py` | FastAPI `/api/v1/market/*` + web proxy | FUNCTIONAL | P1 |
| Market Data | Bybit public WS + reconnect/stale | `ws_manager.py`, `ws_protocol.py`, `real_ws.py` | `test_phase3d1_websocket_stream.py` | Stream hub → web `use-market-stream` | FUNCTIONAL | P1 |
| Market Data | Spot + linear isolation | Category URLs + allowlists | spot/linear URL tests | Hub per category | COMPLETE | P2 |
| Market Data | Confirmed-candle filter | `agent/confirmed_candles.py`, `candles.py` | 3D + 4C + `test_confirmed_candles.py` | Auto engine + pipeline | COMPLETE (agent path); PARTIAL vs REST/auto grace=0 | P0 |
| Market Data | Historical kline load / backfill | REST limit + auto_engine backfill cap | 4C tests | Auto engine | FUNCTIONAL | P1 |
| Market Data | Rate-limit / cache | Soft constants; limited caching | Partial | — | PARTIAL | P2 |
| Market Data | Live Bybit uptime under load | — | — | Manual | NOT VERIFIED | P2 |
| Strategy | EMA / RSI indicators | `agent/market_data.py`, API `indicators.py` | unit + 3D/4A | Agents + overlays | COMPLETE | P0 |
| Strategy | SMA / MACD / volume suite | Not as shared library | — | — | MISSING | P3 |
| Strategy | ATR (risk % only) | `_atr_pct` in `risk_agent.py` | 4A risk tests | Risk only | PARTIAL | P1 |
| Strategy | Standalone EmaRsiStrategy | `agent/strategies/ema_rsi.py` | agent strategy tests (legacy) | CLI / evidence path | FUNCTIONAL | P1 |
| Strategy | Multi-agent 4B.1.0 scoring | `coordinator.py` + weights | `test_phase4a_*`, 4B | SignalPipeline | COMPLETE | P0 |
| Strategy | Multi-timeframe | Single interval per eval | — | — | MISSING | P3 |
| Strategy | Configurable strategy registry | Config dataclass only | — | Not a plugin system | PARTIAL | P2 |
| Agents | Market Agent | `market_agent.py` | 4A | Pipeline | COMPLETE | P0 |
| Agents | Trend Agent | `trend_agent.py` | 4A | Pipeline | COMPLETE | P0 |
| Agents | Momentum Agent | `momentum_agent.py` | 4A | Pipeline | COMPLETE | P0 |
| Agents | Coordinator | `coordinator.py` | 4A/4B | Pipeline | COMPLETE | P0 |
| Agents | Signal Risk Agent | `risk_agent.py` | 4A | Pipeline absolute veto | COMPLETE | P0 |
| Agents | LLM agents | Flag only `LLM_AGENTS_ENABLED` | — | No client module | DESIGN ONLY | P2 |
| Risk | Position notional sizing (paper) | risk_budget / stop_pct | 4A | Pipeline | FUNCTIONAL | P0 |
| Risk | Stop / TP distances (hypothetical) | ATR-based + RR | 4A | Decision levels | FUNCTIONAL | P0 |
| Risk | Min RR / volatility filter | config gates | 4A | Pipeline | COMPLETE | P0 |
| Risk | Cooldown / duplicate key | seen_keys + cooldown_ms | 4A/4B | Persist | COMPLETE | P0 |
| Risk | Daily hypothetical loss halt | paper_balance fraction | 4A | State + SQLite | FUNCTIONAL | P0 |
| Risk | Max concurrent positions / portfolio exposure | — | — | — | MISSING | P1 |
| Risk | Max drawdown (equity) | — | — | — | MISSING | P1 |
| Risk | Fees / slippage in risk | — | — | — | MISSING | P1 |
| Risk | Leverage limits | — | — | — | MISSING | P2 |
| Risk | Kill / halt | halted flag; auto refuses live | 4A/4C | Engine + state | FUNCTIONAL | P0 |
| Risk | Independence from LLM | Pipeline docstring + no LLM calls | — | — | COMPLETE | P0 |
| Paper Trading | Paper risk state persistence | `paper_risk_state` table | 4B/4C/4D | SQLite | COMPLETE | P0 |
| Paper Trading | Simulated order → fill → position lifecycle | Not in signal path | — | UI fixture / 6A mock only | MISSING | P0 |
| Paper Trading | Fees/slippage fills | Mock adapter optional | 6A tests | Gated OFF | PARTIAL | P1 |
| Paper Trading | Unrealized/realized PnL journal | `record_hypothetical_pnl` helper; no full journal UI | limited | — | PARTIAL | P0 |
| Paper Trading | Restart recovery (risk state) | load_risk_state / corrupt halt | 4B/4C | SQLite | FUNCTIONAL | P1 |
| Paper Trading | `/paper` UI | Fixture / broker_implemented false | — | Disconnected | DESIGN ONLY | P1 |
| Backtesting | Full OHLCV replay engine | — | — | `/backtesting` empty | MISSING | P0 |
| Backtesting | Equity / DD / win rate metrics | Fixture analytics only | — | — | DESIGN ONLY | P1 |
| Analytics | Signal history analytics API | signals analytics routes | 4B | Studio | FUNCTIONAL | P1 |
| Analytics | Performance equity curve (real) | `analyticsFixture` | — | `/analytics` | DESIGN ONLY | P1 |
| Persistence | SQLite signal history + contributions | `signal_history_store.py` v4 | 4B/4C/4D | SoT | COMPLETE | P0 |
| Persistence | Atomic outbox | `cloud_sync_outbox` | 4D local | Sync worker OFF | COMPLETE | P1 |
| Persistence | Supabase mirror schema | Alembic through 0005 | Gate B/C1 | Writes OFF | FUNCTIONAL | P3 |
| Backend | FastAPI signals + market | routers | many tests | Web proxies | FUNCTIONAL | P0 |
| Backend | Auth JWKS | `jwt_verifier.py` | part5b | Private reads OFF | FUNCTIONAL | P2 |
| Frontend | Markets live UI | market components + stream | — | Live API | FUNCTIONAL | P1 |
| Frontend | Agent Studio signals/engine | `SignalsPanel`, automation panel | — | API | FUNCTIONAL | P0 |
| Frontend | Studio workflow evidence | projector + inspector | — | Often empty without worker | PARTIAL | P1 |
| Frontend | Strategy editors | — | — | — | MISSING | P2 |
| OpenAI | Client + Signal Intelligence | No runtime client found | — | Flag false | MISSING | P2 |
| Testing | Core signal/market suites | listed below | **97 passed** (Prompt 64 sample) | Local | FUNCTIONAL | P0 |
| Execution | Live Testnet/Mainnet orders | 6A adapter stubs | 6A mocked | Flags OFF | BLOCKED | — |

### Safe local test sample (2026-11-08)

```text
uv run pytest tests/test_phase3d_market_data.py \
  tests/test_phase3d1_websocket_stream.py \
  tests/test_phase4a_multi_agent_signals.py \
  tests/test_phase4b_signal_history.py \
  tests/test_phase4c_auto_signal_engine.py \
  tests/test_phase4d_complete_local.py \
  tests/test_phase6a_automation_foundation.py -q
→ 97 passed
```
