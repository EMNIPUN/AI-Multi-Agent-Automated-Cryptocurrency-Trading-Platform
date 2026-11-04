# Phase 0 — Existing Bybit Trading System Audit Report

| Field | Value |
|-------|-------|
| Audit date | 2026-11-03 |
| Scope | Static inspection of repository source, config templates, local journal artifacts |
| Method | Read-only; no package installs; no Bybit authenticated/public live calls; no order actions |
| Auditor role | Senior Quantitative Trading Systems Architect & Security Auditor |
| Repo path | `E:\Financial Side\Trading\bybit-trading-bot` |

**Classification legend used below**

| Label | Meaning |
|-------|---------|
| IMPLEMENTED AND VERIFIED | Present in code **and** corroborated by local non-network evidence (e.g. journal artifacts) or unambiguous static proof |
| IMPLEMENTED BUT UNVERIFIED | Present in code; not re-validated against Bybit during this audit |
| PARTIALLY IMPLEMENTED | Incomplete relative to stated objective |
| NOT IMPLEMENTED | No substantive implementation found |
| UNKNOWN | Insufficient evidence |

---

## 1. Executive Summary

The repository is a **Python CLI trading toolkit** with two entry points:

1. **Manual terminal trader** (`main.py`) — interactive spot + USDT perpetual trading via `pybit`.
2. **Single rule-based automation loop** (`run_agent.py`) — EMA/RSI crossover agent with dry-run defaults, CSV journaling, and basic risk gates.

It is **not** yet a multi-agent system, **not** research-ready (no backtester, no historical store), and **not** production-ready for unattended live trading.

**Strengths**

- Clear split between `bot/` (exchange helpers) and `agent/` (automation).
- Env-based Testnet / Demo / Mainnet selection.
- Agent dry-run default + mainnet live lock (`AGENT_ALLOW_LIVE`).
- Instrument lot/tick normalization for qty/price.
- Local journal evidence of sustained dry-run operation (164 `signal` rows on 2026-10-27).

**Critical gaps**

- Git repository has **no commits yet**; first commit risk if `.env` is mishandled.
- No automated tests, mocks, or CI.
- No true paper-trading fill simulator; “dry-run” only logs intent.
- Strategy may use the **forming (incomplete) candle** (look-ahead / instability risk).
- Risk engine is in-process and equity-% sized; **not** stop-distance / volatility based.
- No WebSocket, no persistent state, no order idempotency keys on agent orders, no reconciliation.

**Readiness**

| Question | Answer |
|----------|--------|
| Ready for Testnet automated trading? | **Conditionally yes** after Testnet keys + dry-run→live Testnet dry-run-off validation (not proven in this audit) |
| Ready for live automated trading? | **No** |

---

## 2. Project Overview

### Stated long-term objective (user)

Fully automated multi-agent Bybit spot + futures system with research, risk, execution, monitoring, Testnet/paper/live modes, and human oversight.

### Actual current state (evidence-based)

| Capability | Current state |
|------------|---------------|
| Spot / futures manual trade | Implemented (code) |
| Public market data (REST) | Implemented (code) |
| Single EMA+RSI agent loop | Implemented; dry-run verified via journal |
| Multi-agent coordination | Not implemented |
| Backtesting / research harness | Not implemented |
| Persistent DB / metrics store | Not implemented |
| WebSocket realtime | Not implemented |
| Independent risk microservice | Not implemented (in-process `RiskManager` only) |

### Language / runtime

- Language: **Python 3**
- Observed host Python: **3.11.9**
- Observed project venv Python: **3.13.0**
- No `requires-python`, `pyproject.toml`, or `setup.cfg` pinning a supported version range
- Dependencies (`requirements.txt`): `pybit>=5.17.0`, `python-dotenv>=1.0.0`

---

## 3. Current Project Structure

### Directory tree (excluding `.venv/`, `__pycache__/`, secrets contents)

```text
bybit-trading-bot/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── main.py                 # Manual CLI entry
├── run_agent.py            # Agent CLI entry
├── test_connection.py      # Auth connectivity script (hits Bybit if run)
├── bot/
│   ├── __init__.py
│   ├── config.py           # Env flags, API key load
│   ├── client.py           # pybit HTTP session factory
│   ├── api.py              # Retried request helper
│   ├── utils.py            # CLI prompts, decimals, confirm
│   ├── market.py           # Tickers, books, klines, filters
│   ├── account.py          # Balance, positions, open orders
│   └── trading.py          # Manual place/cancel/leverage/close
├── agent/
│   ├── __init__.py
│   ├── config.py           # Agent settings from env
│   ├── market_data.py      # Candles, EMA/RSI, equity/position helpers
│   ├── runner.py           # Polling loop
│   ├── risk.py             # Sizing + daily loss halt + trade plans
│   ├── executor.py         # Dry-run / place_order
│   ├── journal.py          # CSV logger
│   └── strategies/
│       ├── __init__.py
│       ├── base.py         # Signal / SignalAction
│       └── ema_rsi.py      # Sole strategy
└── logs/                   # Generated; gitignored
    └── agent_YYYYMMDD.csv
```

### Entry points

| File | Purpose | Risk if executed during audit |
|------|---------|-------------------------------|
| `main.py` | Interactive trading | Can place live orders — **do not run for audit** |
| `run_agent.py` | Automation loop | Can place orders if flags enabled — **do not run for audit** |
| `test_connection.py` | Public + private API probe | Authenticated call — **not run** |

### Configuration

| Source | Role |
|--------|------|
| `.env` (local, gitignored) | Live credentials + agent flags |
| `.env.example` | Template with placeholders |
| `bot/config.py` | `BYBIT_*` load |
| `agent/config.py` | `AGENT_*` load |

### Git / deployment

- `.git` exists; branch `main` has **no commits** (`fatal: your current branch 'main' does not have any commits yet`).
- `.env` is ignored by `.gitignore` (evidence: `git check-ignore -v .env` → `.gitignore:1:.env`).
- No Dockerfile, compose, systemd unit, CI workflow, or monitoring config found.
- `logs/` gitignored.

### Structural weaknesses

1. **Duplication**: `get_last_price` exists in both `bot/market.py` and `agent/market_data.py` with different return types.
2. **`test_connection.py` is not a unit test** — it is a live network script.
3. **No package metadata** (`pyproject.toml`) / lockfile.
4. **No separation of research vs trading runtimes**.
5. **Unused / thin modules**: `bot/__init__.py`, `agent/__init__.py` are stubs; only one strategy module.

---

## 4. Implemented Functionality Matrix

| # | Feature | Classification | Evidence |
|---|---------|----------------|----------|
| 1 | Bybit connection handling | IMPLEMENTED BUT UNVERIFIED | `bot/client.py` L6–18 builds `HTTP(...)` with retries; not re-called this audit |
| 2 | Public market-data retrieval | IMPLEMENTED BUT UNVERIFIED | `bot/market.py` `get_tickers` / `get_orderbook` L16–64 |
| 3 | Historical candlestick retrieval | IMPLEMENTED BUT UNVERIFIED | `bot/market.py` L67–84; `agent/market_data.py` `fetch_candles` L16–47 |
| 4 | Spot market functionality | IMPLEMENTED BUT UNVERIFIED | `main.py` L37–57; `bot/trading.py` `place_spot_order` L29–122 |
| 5 | Futures market functionality | IMPLEMENTED BUT UNVERIFIED | `main.py` L60–88; `bot/trading.py` L140–347 |
| 6 | Account balance retrieval | IMPLEMENTED BUT UNVERIFIED | `bot/account.py` L27–61; agent `get_equity` L102–112 |
| 7 | Position monitoring | IMPLEMENTED BUT UNVERIFIED | `bot/account.py` L64–99; `agent/market_data.py` L128–173 |
| 8 | Order creation and cancellation | IMPLEMENTED BUT UNVERIFIED | `place_order` / `cancel_order` / `cancel_all_orders` in `bot/trading.py`; agent `executor.py` L78–127 |
| 9 | Strategy signal generation | IMPLEMENTED AND VERIFIED | `agent/strategies/ema_rsi.py`; journal contains 164 `signal` events (`logs/agent_20261027.csv`) |
| 10 | Automated agent behavior | IMPLEMENTED AND VERIFIED (dry-run path) | `agent/runner.py` loop; journal `start`/`signal`/`stop` |
| 11 | Risk validation | PARTIALLY IMPLEMENTED | `agent/risk.py` equity%, max positions, min qty, daily loss; missing SL-distance sizing, correlation, fees |
| 12 | Stop-loss / take-profit | PARTIALLY IMPLEMENTED | Manual optional TP/SL (`bot/trading.py` L209–214); agent futures % TP/SL (`agent/risk.py` L170–196, `executor.py` L90–93); spot agent TP/SL absent |
| 13 | Paper trading support | PARTIALLY IMPLEMENTED | Dry-run logs intent only (`executor.py` L61–74); no simulated fills/PnL |
| 14 | Testnet support | IMPLEMENTED BUT UNVERIFIED | `BYBIT_TESTNET` in `bot/config.py` L14; `.env.example` L5–6 |
| 15 | Live trading support | IMPLEMENTED BUT UNVERIFIED | Mainnet path + manual confirm (`bot/trading.py` L19–26); agent live lock (`agent/config.py` L81–90) |
| 16 | Error handling | PARTIALLY IMPLEMENTED | Retries in `bot/api.py` / client; many bare `except Exception` swallows |
| 17 | Logging and monitoring | PARTIALLY IMPLEMENTED | Print + CSV journal; no metrics/alerting |
| 18 | Recovery after restart | PARTIALLY IMPLEMENTED | Re-reads exchange positions each tick; daily loss state **not** persisted (`RiskState` in-memory, `agent/risk.py` L13–19) |

### Journal artifact summary (local, non-network)

From `logs/agent_20261027.csv` event counts:

| Event | Count |
|-------|------:|
| signal | 164 |
| start | 1 |
| stop | 1 |
| test | 1 |
| dry_run / order / error / halt | 0 |

Interpretation: agent ran in dry-run and produced HOLD-class signals; **no** dry-run trade intents and **no** live agent orders recorded that day.

---

## 5. Existing Trading Strategies

### Implemented strategy (code)

**Name:** `EmaRsiStrategy` — `agent/strategies/ema_rsi.py`

| Aspect | Finding | Evidence |
|--------|---------|----------|
| Indicators | EMA fast/slow, RSI | L19–21; helpers in `agent/market_data.py` L50–99 |
| MACD / ATR / volume filters | Not used in strategy | No references in strategy module |
| Timeframe | Configurable via `AGENT_INTERVAL` (default `"15"`) | `agent/config.py` L64 |
| Entry BUY | Fast EMA crosses above slow **and** RSI &lt; overbought | `ema_rsi.py` L43–57 |
| Entry SELL | Fast EMA crosses below slow **and** RSI &gt; oversold | L59–70 |
| Exit | Opposite signal closes / flips via risk planner | `agent/risk.py` L78–114 |
| Stop-loss | Futures: % from signal price | `agent/risk.py` L170–196 |
| Take-profit | Futures: % from signal price | same |
| Trend filter / regime detection | None beyond EMA cross | — |
| Position sizing | Equity % × leverage / price | `agent/risk.py` L127–135 |
| Signal confidence | None | `Signal` has no confidence field (`strategies/base.py`) |
| Deterministic? | Yes (pure functions of candle closes + settings) | — |
| Confirmed candles only? | **No** — uses last bar in series (`i = len(closes) - 1`) | `ema_rsi.py` L23–24 |
| Look-ahead / future leak | **Risk:** Bybit klines typically include the **in-progress** candle; crossing on an unfinished bar can flip intrabar | `fetch_candles` includes all returned rows L36–46 |
| Fees / funding / slippage | Not considered in signals or sizing | No code |

### Documented but not separately implemented

README describes the same EMA+RSI agent; no additional strategies are documented as implemented.

### Manual trading “strategy”

Human discretionary via CLI — not algorithmic.

---

## 6. Current Agent Architecture

### Is it multi-agent?

**No.** There is a **single automation process** with internal modules:

```text
run_agent.py
  └─ AgentRunner
       ├─ EmaRsiStrategy   (signal)
       ├─ RiskManager      (plan / gates)
       ├─ OrderExecutor    (dry-run or place)
       └─ TradeJournal     (CSV)
```

Evidence: `agent/runner.py` L15–22 constructs one strategy, one risk manager, one executor.

| Multi-agent criterion | Status |
|-----------------------|--------|
| Multiple specialized agents | No |
| Inter-agent messaging bus | No |
| Signal aggregation / voting | No |
| Conflict resolution across strategies | No |
| Independent risk process | No (same process; runner calls risk then executor) |
| ML / LLM agents | No |
| Agent can bypass risk? | **Not via public runner path** — `tick()` always calls `plan_trade` before `execute` (L99–110). A future code change could call executor directly. |
| Agent can modify own risk rules? | **No runtime self-modification**; rules from env/`AgentSettings` |

### Separation of analysis vs execution

- **Partial:** strategy emits `Signal`; executor places orders.
- Risk sits between them in the runner (good pattern), but not a separately deployable control plane.

---

## 7. Exchange Integration Assessment

| Topic | Assessment | Evidence |
|-------|------------|----------|
| SDK | `pybit.unified_trading.HTTP` | `bot/client.py` |
| Environments | Testnet / Demo / Mainnet flags | `bot/config.py` L14–25; client L7–9 |
| Auth | API key/secret from env | `bot/config.py` L12–13 |
| Public REST | Tickers, orderbook, klines, instruments | `bot/market.py` |
| Private REST | Wallet, positions, orders, leverage | `bot/account.py`, `bot/trading.py`, agent helpers |
| Categories | `spot`, `linear` (USDT perps) | menus + trading params |
| Position mode | Hard-coded one-way `positionIdx=0` | `bot/trading.py` L200, L305; `executor.py` L87 |
| Hedge mode | Not supported | — |
| Inverse / options | Not supported | — |
| WebSocket | Not implemented | No WS usage in project `.py` files |
| Rate limits | Relies on pybit retries; no app-level limiter | `bot/client.py` `force_retry` |
| Idempotency | Manual prints `orderLinkId` if returned; agent does **not** set client order link ids | `executor.py` place params L78–93 |
| Withdrawals / transfers | No withdraw/transfer trading calls found in `.py` | Grep only README advice |

---

## 8. Security Audit

### Credentials

| Check | Result | Notes |
|-------|--------|-------|
| Hardcoded secrets in `.py` / `.md` / `.example` | **Not found** in scanned sources | `.env.example` uses placeholders |
| `.env` gitignore | **Pass** | `git check-ignore` confirms |
| `.env` committed historically | **N/A / unknown risk** | Repo has **zero commits**; history cannot yet contain leaks, but first commit must exclude `.env` |
| Secrets in logs | Journal stores equity/prices/reasons; **should not** store API secrets (schema has no secret fields) | `agent/journal.py` L20–33 |
| Secret display in this audit | Redacted; values not reproduced | Per audit rules |

**Exposure category if local `.env` exists:** local credential file (expected).  
**Remediation:** keep gitignored; use OS secret store for production; rotate keys if ever pasted into chat/tickets; ensure first `git add` uses careful staging.

### Trading safety controls

| Control | Status | Evidence |
|---------|--------|----------|
| Mainnet warning (manual) | Present | `main.py` L101–103; `bot/trading.py` L23–25 |
| Manual confirm | Present (`yes`/`y`) | `bot/utils.py` L48–56 |
| Agent dry-run default | Present (default true in loader) | `agent/config.py` L60 |
| Mainnet agent live lock | Present | `live_orders_blocked` L81–90; enforced in `executor.py` L39–40 |
| Withdrawal code | Absent (good) | — |
| API permission scoping | Documented as Read+Trade in README; not enforceable in code | README L42 |
| Duplicate order protection | Weak | No `orderLinkId` on agent orders; poll loop could re-fire after restart before position sync if race occurs |
| Qty/price precision | Present | `normalize_qty` / `normalize_price` in `bot/market.py` |
| Stale market data detection | Absent | No timestamp freshness checks |
| Emergency shutdown | Partial | `AGENT_ENABLED=false`, Ctrl+C, daily loss halt; no remote kill / exchange cancel-all-on-halt |

### P0 security notes

1. **Uncommitted repo + local `.env`:** high chance of accidental secret commit at first push.
2. **`test_connection.py` / `run_agent.py` / `main.py` are live-capable** — filenames do not imply safety.
3. Agent live path places **market IOC** orders without human confirm (`executor.py` L78–96) once flags allow — by design, but dangerous if misconfigured.

---

## 9. Risk Management Audit

| Control | Status | Evidence / gap |
|---------|--------|----------------|
| Max risk per trade | Partial | Equity % margin budget (`AGENT_RISK_PCT`), not $ risk to stop |
| Max account exposure | Not implemented | No portfolio notional cap across symbols |
| Max daily loss | Implemented (in-memory) | `update_equity` L38–54 |
| Max positions | Implemented | `max_open_positions` L117–118 |
| Max leverage | Config-capped ≤20 | `agent/config.py` L69 |
| Sizing by stop distance | Not implemented | Uses % equity × leverage |
| SL required | Futures agent attaches SL; not mandatory for manual | Manual TP/SL optional |
| Balance/margin checks | Partial | Min contract margin check L146–160; no fee buffer |
| Fees / slippage buffers | Not implemented | — |
| Spot+futures aggregation | Not implemented | Single `AGENT_CATEGORY` |
| Correlation limits | Not implemented | — |
| Kill switch | Partial | Daily loss + `AGENT_ENABLED` |
| Cooldown / anti-revenge | Not implemented | — |
| Reject invalid market data | Partial | Candle fetch errors skip symbol; no OHLC sanity checks |
| Order/position reconciliation | Not implemented | No fill verify / open-order sync beyond next-tick position read |
| Independence from agents | Partial | Same process; runner-enforced sequence only |

**Can strategy override risk?** Not through current `AgentRunner` control flow. Risk settings are env-driven and not mutated by strategy code.

---

## 10. Code Quality and Testing Assessment

| Dimension | Assessment |
|-----------|------------|
| Modularity | Fair for MVP (`bot` vs `agent`) |
| Readability | Good; small modules |
| Maintainability | Medium; duplication and broad excepts |
| Type hints | Partial (`str \| None`, dataclasses); not consistent everywhere (`main.py` menus untyped) |
| Input validation | CLI prompts validated; env floats clamped in agent config |
| Exception handling | Mixed; silent `except Exception: return None` in several helpers |
| Config design | Env-centric; workable; no schema validation library |
| Dependency management | Minimal, unpinned upper bounds |
| Unit tests | **None** |
| Integration / mock exchange tests | **None** |
| Backtesting tests | **None** |
| Logging quality | Print + CSV; unstructured for ops |
| Restart recovery | Soft (re-fetch positions); risk day state resets |
| Idempotency | Missing client order ids |
| CI/CD | None |
| Deployment readiness | None |

### Critical missing tests (do not run live scripts as “tests”)

1. EMA/RSI pure-function unit tests with fixture candles.
2. Cross detection on confirmed vs incomplete bars.
3. `RiskManager.plan_trade` sizing / halt / max positions.
4. `live_orders_blocked` matrix (dry-run / testnet / mainnet / allow_live).
5. `normalize_qty` / tick rounding fixtures.
6. Executor dry-run never calls `place_order` (mock session).

---

## 11. Research and Backtesting Readiness

| Capability | Status |
|------------|--------|
| Historical data storage | Not implemented |
| Data quality validation | Not implemented |
| Reproducible backtesting | Not implemented |
| Train/test / walk-forward | Not implemented |
| Fee / slippage / funding simulation | Not implemented |
| Benchmarks / performance metrics | Not implemented |
| Signal history | Partial (CSV journal) |
| Experiment tracking / strategy versioning | Not implemented |
| Agent contribution analysis | N/A (single agent) |

**First research capabilities to add:** offline candle downloader + confirmed-bar backtester for `EmaRsiStrategy` with fees; then journal schema versioning.

---

## 12. Production Readiness Assessment

| Area | Status |
|------|--------|
| Processing efficiency | Adequate for 1 symbol / 60s poll; not HFT |
| API efficiency | Multiple REST calls per tick (equity, position, kline, instruments) |
| WebSocket | Absent |
| Scalability | Single-process, single-strategy |
| Failure recovery | Basic retries; no crash supervisor |
| Persistent state | CSV only |
| Observability / alerting | Absent |
| Secret management | Local `.env` only |
| Automated trading readiness | **Not production-ready** |

Manual order success in past sessions (outside this static audit) does **not** imply production readiness for unattended automation.

---

## 13. Critical Problems and Technical Debt

1. **Incomplete candle used for signals** — unstable entries; possible look-ahead vs bar-close systems.
2. **No automated test suite** — regressions likely as multi-agent work begins.
3. **Dry-run ≠ paper trading** — cannot validate expectancy pre-Testnet.
4. **In-memory daily loss state** — resets on restart (can bypass intended daily stop).
5. **No order idempotency** — duplicate market orders possible under retries/races.
6. **Spot position model for agent** — any base wallet &gt; 0 treated as long (`market_data.py` L149–170), including dust.
7. **Git uninitialized history** — process/control risk at first commit.
8. **Python version drift** (3.11 host vs 3.13 venv) — unspecified support matrix.
9. **Single-threaded REST polling** — no depth/funding stream for derivatives quality.
10. ** aspirational multi-agent architecture absent** — current naming `agent/` is a monolith loop.

---

## 14. Recommended Future Multi-Agent Architecture

Do **not** implement yet. Target control plane:

```text
                    ┌─────────────────────┐
                    │ Research/Eval Agent │
                    └──────────▲──────────┘
                               │ offline only
┌──────────────┐   ┌───────────┴───────────┐   ┌────────────────┐
│ Market Data  │──▶│ Trend / Momentum /    │──▶│ Strategy       │
│ Agent (WS+DB)│   │ Derivatives Analyzers │   │ Coordinator    │
└──────────────┘   └───────────────────────┘   └───────┬────────┘
                                                       │ proposals
                                               ┌───────▼────────┐
                                               │ Risk Engine    │  ← independent, veto power
                                               │ (non-bypassable)│
                                               └───────┬────────┘
                                                       │ approved intents
┌──────────────┐   ┌───────────────────────┐   ┌───────▼────────┐
│ Monitoring   │◀──│ Portfolio Mgmt Agent  │◀──│ Execution Agent│
│ Agent        │   └───────────────────────┘   └────────────────┘
└──────────────┘
```

| Agent | Responsibility |
|-------|----------------|
| Market Data | Normalize WS/REST, store candles, freshness SLAs |
| Trend Analysis | EMA/structure regimes |
| Momentum Analysis | RSI/ROC/volume confirmation |
| Derivatives Analysis | Funding, OI, basis, liquidation heat |
| Strategy Coordinator | Aggregate signals; conflict rules |
| Risk Engine | Hard gates; cannot be overridden by strategists |
| Portfolio Management | Exposure, correlation, allocation |
| Execution | Idempotent orders, cancel/replace, fill tracking |
| Monitoring | Heartbeats, PnL, kill switch, alerts |
| Research/Eval | Backtests, promotions Testnet→limited live |

**Hard rule:** only Execution Agent talks to order endpoints; only Risk Engine can approve.

---

## 15. Prioritized Development Backlog

### P0 — Critical security / trading safety

| ID | Problem | Evidence | Severity | Impact | Solution | Dependencies | Acceptance | Complexity |
|----|---------|----------|----------|--------|----------|--------------|------------|------------|
| P0-1 | Accidental secret commit risk | Zero commits; local `.env` | Critical | Key leak | First commit without `.env`; pre-commit secret scan | git | `.env` never tracked | Low |
| P0-2 | Incomplete-candle signals | `ema_rsi.py` uses last bar | High | Bad fills / flip-flops | Trade only on closed candles (`candles[:-1]`) | market_data | Unit test proves no open-bar cross | Medium |
| P0-3 | Daily loss reset on restart | `RiskState` memory-only | High | Bypass kill switch | Persist day start equity + halt flag | journal/disk | Kill remains after restart | Medium |
| P0-4 | No agent order idempotency | No `orderLinkId` in executor | High | Duplicate orders | Stable client order link ids + de-dupe | executor | Replay safe | Medium |

### P1 — Core architecture / correctness

| ID | Problem | Evidence | Severity | Impact | Solution | Dependencies | Acceptance | Complexity |
|----|---------|----------|----------|--------|----------|--------------|------------|------------|
| P1-1 | No real tests | No `tests/` | High | Silent breakage | Pytest + mocked HTTP | — | CI green offline | Medium |
| P1-2 | Dry-run not paper | executor dry-run only logs | High | False confidence | Paper broker simulating fills/fees | journal | Paper PnL report | High |
| P1-3 | Weak sizing model | equity%×leverage | Medium | Wrong risk | SL-distance / ATR sizing | risk | Risk per trade ≈ target $ | Medium |
| P1-4 | Spot dust = position | `get_position` spot branch | Medium | Spurious sells | Min notional threshold | market_data | Dust ignored | Low |
| P1-5 | Deduplicate price helpers | two `get_last_price` | Low | Drift | Single shared helper | bot/agent | One implementation | Low |

### P2 — Research / validation

| ID | Problem | Evidence | Severity | Impact | Solution | Dependencies | Acceptance | Complexity |
|----|---------|----------|----------|--------|----------|--------------|------------|------------|
| P2-1 | No backtester | absent | High | Cannot validate edge | Historical kline store + replay | P0-2 | Report sharpe/DD with fees | High |
| P2-2 | No fee/funding/slip models | absent | High | Overstated performance | Cost model module | P2-1 | Costs applied in backtest | Medium |
| P2-3 | Signal schema weak | CSV only | Medium | Hard research | Versioned event store | journal | Queryable signals | Medium |

### P3 — Multi-agent / advanced

| ID | Problem | Evidence | Severity | Impact | Solution | Dependencies | Acceptance | Complexity |
|----|---------|----------|----------|--------|----------|--------------|------------|------------|
| P3-1 | Not multi-agent | single runner | Medium | Scalability | Introduce coordinator + isolated risk | P1 | ≥2 analyzers + veto risk | High |
| P3-2 | No WS | REST only | Medium | Latency/staleness | Market data agent WS | P3-1 | Freshness SLA | High |
| P3-3 | LLM trading | absent (good) | — | — | Only advisory, never execution authority | risk | Cannot place orders | Medium |

**Priority principle:** fix correctness/safety of the current loop before adding AI agents.

---

## 16. Phase 1 Recommended Implementation Plan

**Goal:** make the *existing* single-agent loop safe and verifiable on Testnet — still **no** multi-agent expansion.

1. **Repo hygiene:** initial commit excluding `.env` / `logs/`; add secret-scan hook guidance in README.
2. **Confirmed-bar strategy:** ignore in-progress candle; add unit tests with fixtures.
3. **Persist risk halt state** across restarts.
4. **Executor idempotency** via `orderLinkId`.
5. **Offline pytest suite** with mocked `pybit` session (never hit network in CI).
6. **Testnet runbook:** dry-run → Testnet live (`AGENT_DRY_RUN=false`, Testnet keys) → journal must show controlled `order` then flat.
7. **Minimal paper ledger** (optional stretch): apply hypothetical fills at next bar open.

**Explicit non-goals for Phase 1:** LLM agents, multi-strategy voting, mainnet `AGENT_ALLOW_LIVE`, WebSockets.

---

## 17. Open Questions and Unknowns

1. Exact Bybit API key permissions on the operator account (Read/Trade/Withdraw) — not inspectable offline.
2. Whether the Unified account is UTA and one-way mode is actually enabled on the exchange side.
3. Whether production intent is always single-symbol or multi-symbol concurrent.
4. Acceptable max live automation notional / leverage policy.
5. Whether Demo Trading (`BYBIT_DEMO`) will be preferred over Testnet for paper-like practice.
6. Hosting target (local PC vs VPS) — affects secret management and uptime.
7. Prior mainnet manual fills were reported in earlier sessions; **this Phase 0 audit did not re-verify** them against the exchange.

---

## 18. Final Assessment

| Dimension | Rating |
|-----------|--------|
| Current development stage | **MVP / Phase-0 foundation** (manual CLI + single dry-run agent) |
| Architectural maturity | **Low–Medium** — clean folders, monolith automation |
| Security maturity | **Medium for hobby CLI** — env + dry-run locks; weak for unattended prod |
| Research readiness | **Low** — journal only |
| Risk management maturity | **Low–Medium** — basic gates; not institutional |
| Ready for Testnet automated trading? | **Conditionally** after Phase 1 safety fixes + Testnet keys |
| Ready for live automated trading? | **No** |

### Top five immediate priorities

1. Protect secrets at first git commit / rotate if exposed elsewhere.  
2. Signal only on **confirmed** candles.  
3. Persist kill-switch / daily loss state.  
4. Add offline unit tests around strategy, risk, and live-order locks.  
5. Prove agent open/close on **Testnet** with journal evidence before any mainnet automation.

### Recommended next development milestone

**Phase 1 — “Safe Single-Agent Testnet Loop”:** confirmed bars + persisted risk halt + idempotent orders + pytest mocks + documented Testnet validation. Multi-agent work starts only after that milestone passes.

---

*End of Phase 0 audit. No source files other than this report were modified. No exchange calls were made during this audit.*
