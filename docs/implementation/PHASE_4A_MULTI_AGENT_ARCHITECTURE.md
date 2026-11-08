# Phase 4A — Multi-Agent Architecture (Signals Only)

## Scope

Deterministic, explainable multi-agent **signal generation** using public market data.

**No** real Bybit order submission. **No** private wallet/position reads for sizing. **No** LLM decisions.

## Pipeline order (explicit)

1. **Market Data Agent** — validate confirmed candles, spot/linear isolation, freshness
2. **Trend Agent** — EMA20 / EMA50 / EMA200 structure
3. **Momentum Agent** — RSI14 + price/volume context
4. **Coordinator** — weighted score → proposed BUY / SELL / HOLD / BLOCKED
5. **Risk Agent** — paper-capital veto (absolute; never overridden)

## Module map

| Concern | Path |
|---------|------|
| Types | `agent/multi_agent/types.py` |
| Config / weights | `agent/multi_agent/config.py` |
| Market agent | `agent/multi_agent/market_agent.py` |
| Trend agent | `agent/multi_agent/trend_agent.py` |
| Momentum agent | `agent/multi_agent/momentum_agent.py` |
| Paper risk agent | `agent/multi_agent/risk_agent.py` |
| Coordinator | `agent/multi_agent/coordinator.py` |
| Orchestrator | `agent/multi_agent/pipeline.py` |
| Fixtures | `agent/multi_agent/fixtures.py` |
| HTTP API | `apps/api/app/signals/` |
| Studio UI | `apps/web/src/features/agent-studio/components/SignalsPanel.tsx` |

## Reuse

- Confirmed candles: `agent/confirmed_candles.py`
- EMA/RSI: `agent/market_data.py`
- Public REST: `apps/api/app/market_data/rest_client.py`
- Existing AgentRunner / live `RiskManager` unchanged and not required for 4A signals

## HTTP surface

- `GET /api/v1/signals/status` — kill-switch visibility
- `POST /api/v1/signals/evaluate` — fixture/offline candles
- `GET /api/v1/signals/evaluate` — public Bybit klines only

Root API remains `trading_endpoints: false`.

## Invariants

- `execution_allowed` always `false`
- Decisions labeled `not_an_order: true`
- Risk VETO / HALTED → final action `BLOCKED`
- Signal strength ≠ calibrated win probability
