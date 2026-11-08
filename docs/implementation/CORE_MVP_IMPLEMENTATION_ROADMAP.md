# CryptoNova — Core MVP Implementation Roadmap

| Field | Value |
| --- | --- |
| Based on | Prompt 64 core audit (2026-11-08) |
| Goal | Complete essential trading loop **before** cloud production / Gate 63 cutover |
| Constraint | No live orders; no cloud writes; OpenAI optional and read-only later |

---

## Core MVP definition

**In scope**

1. Load public market data (existing).
2. Indicators + `4B.1.0` agents (existing).
3. Deterministic BUY/SELL/HOLD + risk veto (existing).
4. Persist to SQLite (existing).
5. **New:** local paper broker lifecycle from approved signals.
6. **New:** performance stats from paper journal.
7. **New:** Studio panels for positions / PnL (wire to real local data).
8. **New:** minimal confirmed-bar backtester reusing pipeline.
9. **Later:** read-only OpenAI signal explanations.

**Out of scope for MVP**

- Supabase writes/sync, Gate 63 cutover, live Testnet/Mainnet orders, multi-tenant SaaS, LLM-directed trading.

---

## Prioritized sequence

### Milestone 1 — Paper trading lifecycle (LARGE) — **P0**

| | |
| --- | --- |
| **Objective** | Turn an APPROVED signal into a simulated order → fill → position → optional SL/TP exit → realized PnL → balance update, all in SQLite. |
| **Reuse** | `CoordinatorDecision` levels; `PaperRiskConfig`; `SignalHistoryStore`; 6A mock fill ideas (`simulate_full_fill`) without enabling exchange. |
| **Progress (65A)** | **DONE:** `agent/paper/*` broker, fills, Decimal accounting, separate SQLite schema, idempotency/restart, portfolio guards, opt-in integration adapter (default OFF), synthetic demo, 35 focused tests, contracts/docs. |
| **Progress (65B)** | **DONE:** `PAPER_READ_API_ENABLED` gate (default OFF); `apps/api/app/paper/*` GET-only loopback API; `PaperReadStore` (mode=ro, no DDL); Next.js `/api/paper/*` proxy + `/paper` journal UI; Studio link + signal↔paper lookup (no auto-create); frontend vitest + `test_core_paper_api.py`. |
| **Still intentional OFF** | Broker auto-attach; POST mutations; Futures paper sim; cloud mirror of paper rows. |
| **Likely files** | `agent/paper/*`, `apps/api/app/paper/*`, `apps/web/src/app/paper/*`, `apps/web/src/app/api/paper/*` |
| **Dependencies** | Signal persistence COMPLETE |
| **Risks** | Confusing with Phase 6A live path — keep separate module; never call Bybit private APIs |
| **Acceptance** | 65A + 65B acceptance met for local paper lifecycle + read UI. |
| **Tests** | `tests/test_core_paper_*.py`, `apps/web/src/lib/paper/paper-ui.test.ts` |
| **Effort** | LARGE — **Milestone 1 COMPLETE** for local paper journal |

### Milestone 2 — Deterministic risk hardening (MEDIUM) — **P0**

| | |
| --- | --- |
| **Objective** | Add portfolio caps + fee-aware sizing using reconciled paper equity (not hypothetical signal balance). |
| **Reuse** | `risk_agent.py` as stage-1 veto; `agent/paper/*` ledger |
| **Progress (66)** | **DONE:** `evaluate_portfolio_entry`, equity reconciliation, fee/slip net RR sizing, exposure/position caps, durable daily-loss & drawdown halt (schema v2), atomic fill recheck, opt-in adapter OFF by default, demo + focused tests. Signal pipeline untouched. |
| **Still later** | Wire portfolio equity into signal-stage notional by default (optional); Futures portfolio risk |
| **Likely files** | `agent/paper/risk.py`, `equity.py`, `portfolio.py`, `risk_config.py`, store v2 |
| **Dependencies** | Milestone 1 COMPLETE |
| **Acceptance** | Met for local paper portfolio risk (Prompt 66). |
| **Tests** | `tests/test_core_portfolio_risk.py`, `test_core_paper_risk_integration.py` |
| **Effort** | MEDIUM — **COMPLETE** for paper portfolio gate |

### Milestone 3 — Performance analytics from paper journal (MEDIUM) — **P1**

| | |
| --- | --- |
| **Objective** | Compute win rate, profit factor, expectancy, max DD, equity curve from paper fills — replace fixtures. |
| **Reuse** | Signal analytics patterns; Recharts on `/analytics` |
| **Progress (67A)** | **DONE (backend):** `agent/paper/analytics/*` read-only engine; session/symbol/UTC-exit filters; realized vs marked equity + labeled drawdown; FastAPI GETs behind `PAPER_READ_API_ENABLED`; Next proxies; seed + demo; metric/API docs. |
| **Progress (67B)** | **DONE (frontend):** `/analytics` uses real paper analytics APIs; session selector + filters; no SAMPLE fixture fallback; honest disabled/empty/error states; equity labeled session-wide. |
| **Still later** | Studio cards wiring polish |
| **Likely files** | `agent/paper/analytics/*`, `apps/api/app/paper/*`, `apps/web/src/app/analytics/*`, `apps/web/src/lib/paper/*` |
| **Dependencies** | Milestone 1 COMPLETE |
| **Acceptance** | 67A+67B met for local paper analytics (API + dashboard). |
| **Tests** | `tests/test_core_paper_analytics*.py`, `apps/web/src/lib/paper/analytics-ui.test.ts` |
| **Effort** | MEDIUM — **Milestone 3 COMPLETE** for paper analytics |

### Milestone 4 — Confirmed-bar backtester (LARGE) — **P1**

| | |
| --- | --- |
| **Objective** | Replay historical OHLCV through `SignalPipeline` (or extracted strategy fn) with paper broker; no look-ahead. |
| **Reuse** | REST klines; confirmed candle rules; pipeline; paper broker |
| **Progress (68A)** | **DONE (backend engine):** `agent/backtest/*` deterministic replay; offline fixtures; isolated paper journal; optional portfolio risk injection; 67A metrics; demo CLI; look-ahead tests. |
| **Progress (68B)** | **DONE (read API + UI):** FastAPI GET `/api/v1/backtests/*` behind `BACKTEST_READ_API_ENABLED`; Next proxies; `/backtesting` inspects saved reports; provenance + assumptions; order/decision reconciliation. |
| **Progress (68C)** | **DONE (controlled run):** public historical loader + dataset cache; `BACKTEST_RUN_API_ENABLED` POST `/runs` + job status; worker limits; `/backtesting` Run panel; provenance labels; docs. |
| **Still later** | News Intelligence Agent (proposed next); broader symbol catalog; Futures leverage sim |
| **Likely files** | `agent/backtest/history_provider.py`, `dataset_cache.py`; `apps/api/app/backtests/run_*`; `apps/web/.../RunBacktestPanel.tsx` |
| **Dependencies** | Milestones 1–3 + 68A + 68B |
| **Risks** | Look-ahead if forming bars leak; reuse confirmed-only path; public API rate limits |
| **Acceptance** | 68A+68B+68C met for local deterministic engine + read UI + gated historical run |
| **Tests** | `tests/test_core_backtest_68a.py`, `test_core_backtest_api_68b.py`, `test_core_backtest_history_68c.py`, `test_core_backtest_run_api_68c.py`, `apps/web/src/lib/backtest/backtest-ui.test.ts` |
| **Effort** | LARGE — **Milestone 4 COMPLETE** for local backtest loop (68A–68C) |

### Milestone 5 — Agent Studio core wiring (MEDIUM) — **P1**

| | |
| --- | --- |
| **Objective** | Show live paper positions, trade history, and real analytics; keep signals/engine as-is. |
| **Reuse** | `SignalsPanel`, Studio shell, market stream |
| **Missing** | Replace paper/analytics fixtures; clearer empty vs live evidence on workflow |
| **Likely files** | `apps/web/src/app/paper/page.tsx`, analytics, Studio components |
| **Dependencies** | Milestones 1 & 3 |
| **Acceptance** | No SAMPLE metrics when journal empty; positions match API |
| **Effort** | MEDIUM |

### Milestone 6 — Strategy engine cleanup + candle-grace unify (SMALL–MEDIUM) — **P2**

| | |
| --- | --- |
| **Objective** | Extract pure `evaluate_4b(candles, config) -> decision` for backtest/paper reuse; document EmaRsi vs 4B; align confirmed-bar grace across REST, auto engine, and `filter_confirmed_candles` (prefer ≥1–2s). |
| **Reuse** | `pipeline.py` internals; `agent/confirmed_candles.py` |
| **Missing** | Thin facade + docs; grace policy single source of truth |
| **Acceptance** | Backtest and live auto engine call same function; REST/auto/agent confirmation policy documented and tested at boundary |
| **Effort** | SMALL–MEDIUM |

### Milestone 7 — Read-only OpenAI Signal Intelligence (MEDIUM) — **P2**

| | |
| --- | --- |
| **Objective** | Explain persisted signals (indicators, conflicts, risk) via structured JSON; disabled by default. |
| **Reuse** | Decision payload JSON; Studio inspector |
| **Progress (69D)** | **DONE (advisory only):** `agent/llm_intelligence` structured comparison after the deterministic decision. Flag default OFF. No order, risk, or size changes. |
| **Must not** | Place orders; change risk; mutate strategy; write cloud |
| **Acceptance** | Flag OFF → no network; Flag ON + key → explanation for decision_id; invalid JSON rejected |
| **Effort** | MEDIUM |

### Milestone 8 — Regression harness (SMALL) — **P1 ongoing**

| | |
| --- | --- |
| **Objective** | One `pytest` marker/`make core-tests` covering market+pipeline+paper+backtest golden |
| **Reuse** | Existing 3D/4A/4B/4C suites |
| **Effort** | SMALL |

---

## Suggested next development milestone

**69E shadow evaluation is implemented.** Historical news backtesting is **not valid** until append-only revisions exist and an operator applies `20261108_0008`, then `0009`, then `0010` on development. Do not start live trading. Keep `NEWS_LLM_ENABLED` false.

**69A / 69A.1:** News foundation and Supabase article persistence DONE.  
**69B:** Critical alert engine DONE. Migration `20261108_0008` is written and **not applied**.  
**69C:** Advisory NewsContext is attached for observability. Trading decisions are unchanged (`news_changed_decision=false`).  
**69D:** Optional OpenAI decision support DONE as advisory comparison only. `llm_changed_decision=false`. Migration `20261108_0009` is written and **not applied**.  
**69E:** Point-in-time shadow replay DONE as an annotation on 68A. It does not change fills. Migration `20261108_0010` is written and **not applied**. Development news history is incomplete, so news-aware performance claims are blocked.  
**67–68:** paper analytics + backtest loop DONE.

**Deferred until approved:** applying migrations `0008`, `0009`, and `0010`; Gate 63; live execution; any news-aware strategy change.

---

## Deferred (explicit)

| Item | Why defer |
| --- | --- |
| Gate 63 credential cutover | Security track; not required for local MVP |
| Supabase signal sync / C2 | Cloud mirror after local journal exists |
| Live Testnet orders (6A) | After paper expectancy validated |
| Multi-timeframe / MACD suite | After backtest harness exists |
| Large frontend redesign | Wire data first |

---

## Relative effort summary

| Milestone | Effort | Priority |
| --- | --- | --- |
| 1 Paper lifecycle | LARGE | P0 |
| 2 Risk hardening | MEDIUM | P0 |
| 3 Performance analytics | MEDIUM | P1 |
| 4 Backtester | LARGE | P1 |
| 5 Studio wiring | MEDIUM | P1 |
| 6 Strategy extract | SMALL–MEDIUM | P2 |
| 7 OpenAI explain | MEDIUM | P2 |
| 8 Regression pack | SMALL | P1 |
