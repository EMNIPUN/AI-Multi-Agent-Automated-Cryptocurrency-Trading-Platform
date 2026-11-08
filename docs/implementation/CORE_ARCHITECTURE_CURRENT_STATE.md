# CryptoNova — Core Architecture Current State

| Field | Value |
| --- | --- |
| Audit date | 2026-11-08 |
| Branch | `main` @ `345d3a1f443ba9af57d5661154c33ae6facb99a7` |
| Mode | Read-only core audit (Prompt 64) |
| Working tree | Dirty (Phase 3–4D / 63B local changes present; not all committed) |

---

## 1. Runtime topology (verified)

```text
apps/web (Next.js)
  ├─ /markets          → public Bybit via FastAPI market REST/WS bridge
  ├─ /agents (Studio)  → signals + observability + automation panels
  ├─ /paper|/analytics|/backtesting → mostly fixture / empty
  └─ auth UI           → Supabase Auth (reads gated)

apps/api (FastAPI)
  ├─ /api/v1/market/*     public REST + WS hub
  ├─ /api/v1/signals/*    evaluate / history / auto engine (signals only)
  ├─ /api/v1/signals/cloud/*  JWT cloud history (writes OFF)
  ├─ exchange bindings / wallet reads (persistence & orders gated OFF)
  └─ SQLAlchemy → Supabase Postgres (privileged; Gate 63 not cut over)

agent/
  ├─ multi_agent/     deterministic Market→Trend→Momentum→Coordinator→Risk
  ├─ strategies/      legacy EmaRsiStrategy (CLI / evidence)
  ├─ automation/      Phase 6A mocked Testnet pipeline (orders disabled)
  └─ market_data.py   shared EMA/RSI + legacy pybit fetch

Supabase Postgres (app schema)   ★ SoT when SUPABASE_SOT_ENABLED + 0006 applied
```

**Authority today:** Agent durable stores target **Supabase Postgres** when `SUPABASE_SOT_ENABLED=true` (default). Apply `20261108_0006_supabase_sot_cutover` and bind `SIGNAL_CLOUD_OWNER_USER_ID`. Cloud signal mirror writes/sync remain **gated OFF** until dual operator approval.

---

## 2. Core signal lifecycle (code path)

1. **Market data** — Bybit public REST (`BybitPublicRestClient`) and/or WS (`PublicMarketWsManager`) → confirmed klines.
2. **Indicators** — EMA/RSI in `agent/market_data.py` and `apps/api/app/market_data/indicators.py`; ATR% computed ad hoc in `risk_agent`.
3. **Agents** — `SignalPipeline.run` (`agent/multi_agent/pipeline.py`): Market snapshot → Trend → Momentum → Coordinator propose → Risk finalize.
4. **Persistence** — `SignalHistoryStore` writes Supabase Postgres (SoT): decision + contributions + signal-day risk + checkpoints (outbox deprecated/no-op).
5. **Auto engine** — `ClosedCandleAutoEngine` (`auto_engine.py`) evaluates on confirmed closes; refuses start if `AGENT_ALLOW_LIVE`.
6. **UI** — `SignalsPanel` / Studio surfaces history & status; `execution_allowed` always false on signal APIs.

No step places exchange orders. Phase 6A automation is a separate mocked path.

---

## 3. Module boundaries (keep)

| Module | Primary paths |
| --- | --- |
| Market data | `apps/api/app/market_data/*`, `apps/web/src/lib/market/*` |
| Indicators / strategies | `agent/market_data.py`, `agent/strategies/*`, `apps/api/.../indicators.py` |
| Agents | `agent/multi_agent/*` |
| Risk (signal) | `agent/multi_agent/risk_agent.py` |
| Risk (legacy live) | `agent/risk.py` (CLI / live path — not used by 4A pipeline) |
| Paper / mock exec | `agent/automation/*` (mock only) |
| Persistence | `agent/multi_agent/signal_history_store.py` |
| API | `apps/api/app/signals/*`, `market_data/router.py` |
| Frontend | `apps/web/src/features/agent-studio/*`, `components/market/*` |
| Optional LLM | **No client module found**; `LLM_AGENTS_ENABLED=false` |

---

## 4. Architectural debt (defer unless blocking MVP)

1. Dual strategy surfaces: standalone `EmaRsiStrategy` vs multi-agent `4B.1.0` scoring — not unified.
2. “Paper” naming: paper **risk sizing** ≠ paper **broker simulator**.
3. Studio chart often uses observability/worker samples, while `/markets` uses live public stream.
4. Supabase security track (Gates 62/63) is ahead of core trading completeness — correctly deferred for core-first.
5. Phase 6A mock execution coexists with signals-only MVP; keep gated OFF.

---

## 5. Safety invariants (must preserve)

- `AGENT_ALLOW_LIVE=false`, dry-run defaults
- Signal APIs: `execution_allowed=false`, `not_an_order`
- Cloud writes / sync / binding persistence / order submission flags OFF
- Gate 63 runtime cutover not enabled
- Auto engine refuses live-agent flag
