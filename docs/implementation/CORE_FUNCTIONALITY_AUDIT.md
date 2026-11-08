# CryptoNova — Core Functionality Audit (Prompt 64)

| Field | Value |
| --- | --- |
| Date | 2026-11-08 |
| Branch / HEAD | `main` / `345d3a1f443ba9af57d5661154c33ae6facb99a7` |
| Mode | LOCAL AUDIT ONLY |
| Mutations | None remote; no orders; no OpenAI calls; no Gate 63 |

Companions: `CORE_FEATURE_COMPLETION_MATRIX.md`, `CORE_MVP_IMPLEMENTATION_ROADMAP.md`, `CORE_ARCHITECTURE_CURRENT_STATE.md`.

---

## Executive verdict

CryptoNova already has a **working signals-only core**: public market data → deterministic multi-agent BUY/SELL/HOLD → paper risk veto → SQLite persistence → Agent Studio signal surfaces.

It does **not** yet have a complete **paper trading lifecycle**, **backtester**, or **performance analytics** grounded in simulated fills. OpenAI integration is a **flag without a client**. Cloud/security work (4D Gates) is ahead of trading completeness and should stay deferred while the core MVP is finished.

**Overall core system status:** PARTIAL — signals core FUNCTIONAL/COMPLETE; trading loop incomplete.

---

## A. Market Data Engine — FUNCTIONAL

**Evidence paths:** `apps/api/app/market_data/*`, `apps/web/src/lib/market/*`, `agent/confirmed_candles.py`, `agent/multi_agent/auto_engine.py`.

| Capability | Status | Notes |
| --- | --- | --- |
| Bybit REST public | FUNCTIONAL | Tickers, klines, orderbook, trades; no keys |
| Bybit WS public | FUNCTIONAL | Reconnect, subscribe restore, stale detection, orderbook resync (incl. 63-era delta-as-snapshot fix) |
| Spot / linear | COMPLETE | Isolated URLs/categories |
| Confirmed candles | COMPLETE | Forming bars excluded; auto engine on confirm |
| Historical / backfill | FUNCTIONAL | Bounded backfill in auto engine |
| Rate limits / cache | PARTIAL | Soft limits; limited caching |
| Live endurance | NOT VERIFIED | Not load-tested in this audit |

**Risks:**
- REST/WS dual paths (API vs legacy `pybit`).
- Soft rate-limit only (`REST_MIN_INTERVAL_SECONDS`); no 429-aware shared bucket.
- Studio chart often uses observability samples, not the `/markets` public stream.
- **Candle grace misalignment:** agent filter defaults ~2000ms grace (`filter_confirmed_candles`); REST klines and auto-engine job gate often use `grace_ms=0` — boundary race risk across paths.

**Tests:** `test_phase3d_market_data.py`, `test_phase3d1_websocket_stream.py`, `test_confirmed_candles.py` (included in 97-pass sample where listed).

---

## B. Strategy Engine — PARTIAL

**Implemented indicators:** EMA, RSI (shared). Overlay set EMA20/50/200 + RSI14 on API. ATR used as % volatility in risk, not a first-class indicator module. SMA/MACD/volume suite: **MISSING** as shared libs.

**Strategies:**

- `EmaRsiStrategy` — confirmed-bar EMA cross + RSI (`agent/strategies/ema_rsi.py`) — FUNCTIONAL for CLI/evidence; lower bar requirement than EMA200 stack.
- Multi-agent strategy **`4B.1.0`** — weighted Trend+Momentum with market-quality gate (`config.py`, `coordinator.py`) — COMPLETE for signals.
- Doc drift: `PHASE_4A_STRATEGY_SPECIFICATION.md` still describes superseded **4A.1.0** scoring; treat **4B** validation docs + code as authority.

**Coupling:** Multi-agent scoring is agent-coupled, not a pluggable strategy registry. Extract a pure `evaluate_*` facade before backtest reuse.

**Minimal recommended first strategies:**
1. **MVP default:** keep **`4B.1.0` SignalPipeline** (already integrated + heavily tested).
2. **Minimal single-strategy alternative:** `EmaRsiStrategy` for the first backtest/paper A/B once a replay harness exists (simpler, reusable, confirmed-bar only).

---

## C. Multi-Agent Intelligence — COMPLETE (signals-only)

| Agent | Inputs | Outputs | Status |
| --- | --- | --- | --- |
| Market | Confirmed candles, category/symbol | `MarketSnapshot` freshness/quality | COMPLETE |
| Trend | Snapshot closes | Bias + confidence (EMA stack) | COMPLETE |
| Momentum | Snapshot | Bias + RSI/volume context | COMPLETE |
| Coordinator | Contributions + weights | Proposed BUY/SELL/HOLD/BLOCKED | COMPLETE |
| Risk | Proposal + snapshot + state | APPROVED/VETO/HALTED + sizing | COMPLETE |

**Trace:** `SignalPipeline` enforces Market → Trend → Momentum → Coordinator → Risk → finalize; timeouts fail closed; persistence failure → BLOCKED.

**Determinism:** Yes for fixed candles/config/time — no LLM in path (`pipeline.py` header). `execution_allowed` always false.

**Tests:** `test_phase4a_multi_agent_signals.py`, 4B/4C suites.

---

## D. Risk Management — PARTIAL

**Implemented + tested (signal paper risk):** position notional from risk fraction / stop; stop & TP distances; min RR; ATR volatility filter; cooldown; duplicate idempotent key; daily hypothetical loss halt; trend-conflict veto; corrupt-state fail-closed.

**Missing:** portfolio max concurrent positions; account max exposure; equity max drawdown; fees/slippage in sizing; leverage; min exchange order size enforcement; emergency UI kill beyond halted flag / env gates.

**Legacy** `agent/risk.py` is a separate live-oriented manager — not the 4A pipeline.

**LLM independence:** PASS — no OpenAI in risk path.

**Conservative defaults (proposal only — do not change env):** keep 1% risk/trade, 3% daily halt, RR≥1.5, cooldown 15m, ATR cap 6%.

---

## E. Paper Trading Engine — MISSING (lifecycle) / PARTIAL (risk)

| Layer | Reality |
| --- | --- |
| Paper risk evaluation | FUNCTIONAL — sizes + veto + SQLite `paper_risk_state` |
| Simulated broker (order→fill→position→SL/TP→PnL→balance→history) | **MISSING** in signal MVP |
| Phase 6A mock fills | PARTIAL — `MockBybitTestnetAdapter.simulate_full_fill`; gated; not Studio paper journal |
| `/paper` UI | DESIGN ONLY — fixture / `broker_implemented: false` |

**Verdict:** Do **not** mark paper trading COMPLETE. Next core milestone should add a **local paper broker** fed by approved signals.

---

## F. Backtesting — MISSING

No replay engine, equity curve computation, or parameter sweep. `/backtesting` EmptyState. Indicator math ≠ backtester. Research folder is a placeholder.

---

## G. Storage and Backend — FUNCTIONAL / COMPLETE (local signals)

- **SQLite SoT:** `SignalHistoryStore` schema v4 — signal_history, contributions, risk events, paper_risk_state, checkpoints, scheduler, cloud_sync_outbox. Atomic writes tested (4B/4C/4D local).
- **FastAPI:** market + signals + observability + gated exchange/cloud. Auth JWKS present; private reads OFF.
- **Supabase:** schema through Gate 62 (`20261108_0005`); writes/sync OFF — deferred, not discarded.

---

## H. Next.js Agent Studio — PARTIAL

| Surface | Status |
| --- | --- |
| `/markets` live | FUNCTIONAL |
| Studio signals / auto engine | FUNCTIONAL |
| Workflow evidence graph | PARTIAL (empty without worker evidence) |
| `/paper`, `/analytics` | Fixture / SAMPLE |
| `/backtesting` | MISSING |
| Strategy config editors | MISSING |

---

## I. OpenAI Integration — MISSING (design flag only)

- `LLM_AGENTS_ENABLED=false` in env examples.
- **No** `openai` client module / agent package found under `agent/` or `apps/api`.
- Deterministic pipeline explicitly excludes LLM.

**Recommended first feature (future):** read-only **Signal Intelligence Agent** that explains existing persisted decisions (indicators, conflicts, risk veto reasons) with structured JSON schema; never places orders or changes risk.

---

## J. Testing and Reliability — FUNCTIONAL

Safe sample run (no orders/cloud writes):

```text
97 passed — phase3d, 3d1, 4a, 4b, 4c, 4d_complete_local, 6a_automation_foundation
```

Skipped in this audit: optional disposable PG harnesses; any test needing live Bybit endurance; Auth E2E against remote.

Structured logging / duplicate prevention / persistence fail-closed: present on signal path.

---

## Core MVP readiness map

| Step | Desired | Status |
| --- | --- | --- |
| 1 Load market data | Yes | FUNCTIONAL |
| 2 Calculate indicators | Yes | FUNCTIONAL |
| 3 Evaluate strategy | Yes | COMPLETE (4B.1.0) |
| 4 Run agents | Yes | COMPLETE |
| 5 BUY/SELL/HOLD | Yes | COMPLETE |
| 6 Risk checks | Yes | FUNCTIONAL (gaps above) |
| 7 Persist signal | Yes | COMPLETE (SQLite) |
| 8 Simulate paper trades | Yes | **MISSING** |
| 9 Performance | Yes | **MISSING** / fixture |
| 10 Display in Studio | Yes | PARTIAL (signals yes; trades/perf no) |

MVP can run **without** Supabase writes, OpenAI, live orders, or deploy — once paper lifecycle + metrics are built.

---

## Critical blockers for “complete trading system”

1. No paper fill/position/PnL lifecycle tied to signals.
2. No backtester.
3. No real performance analytics.
4. Risk lacks portfolio-level controls and cost model.
5. Frontend paper/analytics/backtest are placeholders.

Non-blockers for signals research: Gate 63, cloud sync, OpenAI.

---

## Safety attestation

- Remote DB mutations: NONE  
- Supabase cloud writes: OFF  
- Cloud sync: OFF  
- Exchange orders: OFF  
- OpenAI API calls: NOT EXECUTED  
- Gate 63: NOT EXECUTED  
- Deploy / git push: NOT EXECUTED  
