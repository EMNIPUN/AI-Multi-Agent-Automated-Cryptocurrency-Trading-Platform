# CURRENT REPOSITORY AUDIT

| Field | Value |
|-------|-------|
| Audit date | 2026-11-04 |
| Workspace | `E:\Financial Side\Trading\AI-Multi-Agent-Automated-Cryptocurrency-Trading-Platform` |
| Method | **Read-only** static inspection of source, config templates, git metadata, and local journal artifacts |
| Constraints honored | No package installs; no Bybit network calls; no order actions; no config changes; secrets not reproduced |
| Related prior audit | `PHASE_0_EXISTING_SYSTEM_AUDIT.md` (2026-11-03) — several git claims are now **stale**; functional findings largely still accurate |
| Auditor roles | Senior Software Architect · Python Backend · AI Systems · Application Security |

**Evidence labels used below**

| Label | Meaning |
|-------|---------|
| **FACT** | Confirmed by source / git / filesystem inspection in this audit |
| **ASSUMPTION** | Reasonable inference not proven by runtime execution |
| **UNVERIFIED** | Present in code; not exercised against Bybit during this audit |
| **STALE DOC** | Prior documentation no longer matches current repo state |

---

## Executive Summary

The repository is a **working Python CLI trading toolkit**, not yet a multi-agent platform and not yet a FastAPI/Next.js SaaS.

**What exists (FACT):**

1. **Manual terminal trader** (`main.py` + `bot/`) — interactive Bybit REST spot and USDT-perpetual trading.
2. **Single rule-based agent** (`run_agent.py` + `agent/`) — EMA/RSI poll loop with dry-run default, CSV journal, and basic risk gates.
3. Env-driven **Testnet / Demo / Mainnet** selection; agent defaults favor safety (`AGENT_DRY_RUN=true`, `AGENT_ALLOW_LIVE=false`, `BYBIT_TESTNET=true` in code / `.env.example`).

**What does not exist (FACT):**

- FastAPI backend, Next.js/TypeScript frontend, PostgreSQL models/migrations, auth, dashboard
- WebSocket market data, paper-trading simulator, backtester, CI/CD, automated unit tests
- Technical Analysis Agent, SMC Agent, Strategy Coordinator, independent Risk Engine service, Portfolio Service, Monitoring stack
- Order idempotency (`orderLinkId` on agent path), persisted kill-switch, position/order reconciliation

**Security verdict:** Defaults are cautious, and **no hardcoded API secrets were found in source**. The system is **not safe for unattended mainnet automation**. Critical gaps: non-idempotent retries on market orders, fail-open position reads, in-memory daily halt, and a weakened `.gitignore`.

**Git / migration state (FACT):** Remote-tracking `main` has 2 commits (`Initial commit`, `Update README.md`). Only `.gitignore` and `README.md` are tracked. Nearly all application code remains **untracked**. Local `.env` exists and is ignored (good). Unstaged `.gitignore` shrinks a full GitHub Python template to four lines — a **regression**.

**Readiness snapshot**

| Question | Answer |
|----------|--------|
| Research MVP (single-agent Testnet dry-run)? | Conditionally yes — code path exists; dry-run journal evidence present |
| Unattended live / mainnet agent? | **No** |
| FastAPI + Next.js dashboard MVP? | **Not started** |
| Multi-agent architecture? | **Not started** (naming aspirational only) |
| Commercial SaaS? | Far future — after safety, API, auth, tenancy |

---

## Repository Tree

### Project source tree (excluding `.venv/`, `__pycache__/`, `.git/`)

```text
AI-Multi-Agent-Automated-Cryptocurrency-Trading-Platform/
├── .env                          # LOCAL SECRET FILE — present, gitignored (values not inspected in report)
├── .env.example                  # Placeholder credentials + agent defaults (untracked)
├── .gitignore                    # MODIFIED unstaged: 4 lines only (.env, .venv/, __pycache__/, logs/)
├── README.md                     # Modified; still references path `bybit-trading-bot`
├── requirements.txt              # pybit>=5.17.0, python-dotenv>=1.0.0 (untracked)
├── main.py                       # Manual CLI entry (untracked)
├── run_agent.py                  # Agent CLI entry (untracked)
├── test_connection.py            # Live auth probe script (untracked) — NOT a unit test
├── PHASE_0_EXISTING_SYSTEM_AUDIT.md
├── CURRENT_REPOSITORY_AUDIT.md   # This report
├── agent_20261027.csv            # Journal artifact at repo ROOT (not under logs/)
├── logs/
│   └── agent_20261027.csv        # ~168 rows; dry-run journal evidence
├── bot/
│   ├── __init__.py
│   ├── config.py                 # API env + testnet/demo flags
│   ├── client.py                 # pybit HTTP session (retries enabled)
│   ├── api.py                    # call_api wrapper + retries
│   ├── utils.py                  # CLI prompts, decimals, confirm
│   ├── market.py                 # Ticker/orderbook/klines + normalize qty/price
│   ├── account.py                # Balance / positions / open orders display
│   └── trading.py                # Interactive spot/futures orders
└── agent/
    ├── __init__.py
    ├── config.py                 # AgentSettings + live_orders_blocked()
    ├── runner.py                 # Poll loop orchestration
    ├── market_data.py            # Candles, EMA/RSI, equity, position
    ├── risk.py                   # Sizing + daily loss RiskState
    ├── executor.py               # Dry-run vs place_order
    ├── journal.py                # CSV under logs/
    └── strategies/
        ├── __init__.py
        ├── base.py               # Signal / SignalAction
        └── ema_rsi.py            # EMA cross + RSI filter
```

### Approximate Python size (non-venv source)

| Area | Approx. lines (non-blank) |
|------|---------------------------|
| `bot/` | ~730 |
| `agent/` | ~640 |
| Root scripts | ~170 |
| **Total application Python** | **~1,540** |

### Entry points (FACT)

| Entry | Role | Network? |
|-------|------|----------|
| `python main.py` | Interactive spot/futures menus | Yes (Bybit REST) if credentials present |
| `python run_agent.py` | Infinite agent poll loop | Yes if credentials present |
| `python test_connection.py` | Server time + API key info | Yes — authenticated probe |

### Dependencies (FACT)

```text
pybit>=5.17.0
python-dotenv>=1.0.0
```

- No FastAPI, SQLAlchemy, Alembic, Next.js, React, PostgreSQL client, pytest, or lint tooling declared.
- No `pyproject.toml`, `package.json`, `Dockerfile`, `.github/workflows/`, or compose file found.
- Local `.venv` contains `pybit` 5.17.0 (FACT from site-packages layout); runtime connectivity **UNVERIFIED** in this audit.

### Configuration (FACT)

| File | Role |
|------|------|
| `.env` | Live secrets/settings (local only; **do not commit**) |
| `.env.example` | Safe template with placeholders |
| `bot/config.py` | Loads `BYBIT_*` |
| `agent/config.py` | Loads `AGENT_*` with clamps |

### Git tracking & migration problems (FACT)

| Item | Status |
|------|--------|
| Branch | `main...origin/main` |
| Commits | `f53fda2` Initial commit; `c610760` Update README.md |
| Tracked files | `.gitignore`, `README.md` only |
| Untracked application | `agent/`, `bot/`, `main.py`, `run_agent.py`, `test_connection.py`, `requirements.txt`, `.env.example`, audit markdown |
| Modified tracked | `.gitignore` (shrunk), `README.md` |
| Duplicate / rename risk | README still documents `bybit-trading-bot` path; workspace folder renamed |
| Duplicate journal | `logs/agent_20261027.csv` and root `agent_20261027.csv` |
| Missing expected for target stack | `backend/`, `frontend/`, `db/`, `tests/`, CI, Docker |
| Sensitive local files | `.env` present; ignored by current `.gitignore` |

### `.gitignore` and sensitive-file posture (FACT)

**Current working-tree `.gitignore` (4 lines):**

```text
.env
.venv/
__pycache__/
logs/
```

| Pattern / asset | Covered? | Risk |
|-----------------|----------|------|
| `.env` | Yes | Low (currently ignored; not in `git ls-files`) |
| `.env.local`, `.env.bak`, `.envrc` | **No** | Accidental commit |
| `*.pem`, credential JSON | **No** | Accidental commit |
| `*.db` / SQLite | **No** (removed vs prior template) | Accidental commit |
| `logs/` | Yes | OK |
| Root `*.csv` / `agent_*.csv` | **No** | Root journal can be committed |
| `__pycache__/`, `.venv/` | Yes | OK |
| Prior full GitHub Python template | **Removed** in unstaged diff | Regression |

**Secrets in source:** No hardcoded API keys/secrets found in `.py` / `.md` / `.env.example` / `requirements.txt`. Credentials load from env vars in `bot/config.py`. **Values in local `.env` were not printed or copied into this report.**

---

## Existing Features Matrix

Legend: **I** = Implemented in code · **P** = Partial · **M** = Missing · **U** = Unverified at runtime this audit

| Component | Status | Evidence | Runtime verified? |
|-----------|--------|----------|-------------------|
| Bybit REST client | **I** | `bot/client.py` `HTTP(...)` | **U** |
| Bybit WebSocket | **M** | No WS usage in project `.py` | N/A |
| Market data (manual) | **I** | ticker / orderbook / klines in `bot/market.py` | **U** |
| Market data (agent poll) | **I** | `fetch_candles` → `get_kline` | **U** (journal implies past dry-run ran) |
| Balances / positions display | **I** | `bot/account.py` | **U** |
| Manual spot trading | **I** | `place_spot_order` | **U** |
| Manual futures trading | **I** | place / close / leverage / TP-SL optional | **U** |
| Qty/price normalization | **I** | `normalize_qty` / `normalize_price` | **U** |
| EMA/RSI strategy | **I** | `ema_rsi.py` + indicator math | Code only |
| Agent runner loop | **I** | `AgentRunner.run_forever` | Journal evidence of prior dry-run |
| Dry-run mode | **I** | Default true; logs intent | Journal rows with `dry_run=1` |
| Risk sizing (% equity) | **P** | Margin-budget style; not $-to-stop | Code only |
| Daily loss kill switch | **P** | In-memory `RiskState` only | Code only |
| TP/SL (agent linear) | **I** | Attached on open | **U** |
| TP/SL (agent spot) | **M** | Not set | N/A |
| Execution service (agent) | **P** | Market IOC; no idempotency | **U** |
| Journal CSV | **I** | `logs/agent_YYYYMMDD.csv` | Local file present (~168 rows) |
| Paper trading simulator | **M** | Dry-run ≠ fills/fees/PnL ledger | N/A |
| Order reconciliation | **M** | — | N/A |
| Emergency flatten / cancel-all on halt | **M** | Halt stops loop only | N/A |
| Multi-agent / SMC / coordinator | **M** | Single hardcoded `EmaRsiStrategy` | N/A |
| FastAPI / Next.js / Postgres | **M** | — | N/A |
| Auth / multi-tenant SaaS | **M** | — | N/A |
| Automated tests / CI | **M** | `test_connection.py` is live probe | N/A |

### Call graph (FACT from imports)

```text
main.py ──► bot.{market,account,trading} ──► bot.client.HTTP (REST)
run_agent.py ──► AgentRunner
                  ├── EmaRsiStrategy
                  ├── RiskManager
                  ├── OrderExecutor ──► session.place_order / set_leverage
                  ├── TradeJournal
                  └── bot.client + bot.market helpers
test_connection.py ──► create_session ──► get_server_time + get_api_key_information
```

Agent does **not** reuse interactive `bot.trading` confirms.

---

## Security Findings (Critical / High / Medium / Low)

### Critical

| ID | Finding | Evidence | Impact |
|----|---------|----------|--------|
| C1 | **Non-idempotent market orders + HTTP retries** | `bot/client.py`: `force_retry=True`, `max_retries=5`; agent `place_order` without `orderLinkId` (`agent/executor.py`) | Timeout-after-accept can **double-fill** |
| C2 | **Position fetch failures treated as flat** | `get_position()` broad `except` → `None` (`agent/market_data.py`); runner treats `None` as no position | Can open **duplicate exposure** during API blips |
| C3 | **Daily loss halt not durable** | `RiskState` in-process; day rollover / restart clears `halted` (`agent/risk.py`) | Kill switch **re-arms** after crash/restart same day |
| C4 | **`.gitignore` regression + root journal unprotected** | Unstaged shrink to 4 lines; root `agent_20261027.csv` not matched by `logs/` | High chance of committing journals / backups / DBs on first bulk add |

### High

| ID | Finding | Evidence | Impact |
|----|---------|----------|--------|
| H1 | Unattended live path once env allows | `run_agent.py` → executor; testnet/demo need only `AGENT_DRY_RUN=false` | Continuous live market orders |
| H2 | No fill / order / position reconciliation | No reconcile module | Orphan orders, partial fills unnoticed |
| H3 | Halt does not flatten or cancel-all | `tick()` journals `halt` and returns `False` | Open risk remains |
| H4 | Strategy uses forming candle | `ema_rsi.py` indexes last bar; Bybit kline includes incomplete candle | Signal flip-flops / unstable entries |
| H5 | Manual CLI is separate live surface | `main.py` + `bot/trading.py`; **not** gated by `AGENT_ALLOW_LIVE` | Shell + `.env` = live trading |
| H6 | Manual leverage uncapped | `set_leverage` passes user string; agent clamps ≤20 | Extreme leverage via CLI |
| H7 | Docs overclaim durable risk | README “daily loss kill switch” vs in-memory state | False sense of safety |

### Medium

| ID | Finding | Evidence |
|----|---------|----------|
| M1 | Spot agent: no TP/SL; leverage set failure does not abort order | `executor.ensure_leverage` warns only |
| M2 | Risk % is margin budget, not risk-to-stop dollars | Oversized notional vs intended loss |
| M3 | Spot “position” = any base wallet > 0 (dust) | Erroneous reduce/sell plans |
| M4 | Silent equity/price failures (`None`) | Halt/sizing may skip without clear fail-closed policy |
| M5 | Incomplete ignore patterns (`.env.bak`, `*.db`, root CSV) | Secret/artifact leak risk |
| M6 | No tests/CI for safety locks | Regressions easy |
| M7 | Confirm UX weaker than README | README says type `yes`; code accepts `y` when `require_yes=True` (`bot/utils.py`) |

### Low

| ID | Finding | Evidence |
|----|---------|----------|
| L1 | No hardcoded secrets in scanned sources | Pass |
| L2 | Defaults: testnet + dry-run + mainnet live lock | Sound baseline |
| L3 | `peak_equity` updated but unused in halt math | Dead field |
| L4 | Repo/product naming vs single-agent reality | Aspirational rename |
| L5 | Journal logs operational trading data (no API keys) | Acceptable for research; protect files |

### Live-execution path summary (FACT)

| Path | Gate |
|------|------|
| Agent + dry-run | No orders (intent log) |
| Agent + dry-run off + testnet/demo | **Live orders allowed** |
| Agent + dry-run off + mainnet + `AGENT_ALLOW_LIVE=true` | **Live mainnet orders** |
| Agent + dry-run off + mainnet + allow_live false | Blocked (`live_orders_blocked`) |
| Manual `main.py` mainnet | Interactive confirm only (`y`/`yes`) |
| `test_connection.py` | Auth check; no place_order |

**Unauthorized remote execution:** No HTTP API / webhook currently exposes trading — risk is **local process + env misconfiguration**, not remote auth bypass. That changes once FastAPI is added without strong auth and kill switches.

---

## Architecture Assessment

### Current architecture (FACT)

Monolithic CLI process with two packages:

- **`bot/`** — exchange adapter + interactive trading UX (coupled).
- **`agent/`** — strategy → risk → execute → journal loop (still process-local).

Strengths: small surface area; clear env flags; reusable normalization helpers; strategy interface seed (`Signal` / `SignalAction`).

Weaknesses:

- Presentation (CLI prompts) mixed with exchange I/O in `bot/trading.py` / `bot/market.py`
- Risk not an independent authority with fail-closed semantics
- No domain events, message bus, or persistence boundary
- No typed API contracts for future dashboard/agents
- Logging via `print` + CSV — not structured observability
- Exception handling often swallows errors into `None` (fail-open for positions)

### Software quality snapshot

| Area | Assessment |
|------|------------|
| Module boundaries | Partial — agent/bot split good; CLI/exchange not isolated |
| Type hints | Present on many public functions; not strict/mypy gated |
| Exception handling | Uneven; trading-critical paths too permissive |
| Logging | `print` + CSV; no levels/correlation IDs |
| Tests | None (offline) |
| CI/CD | None |
| Config | Env + clamps; no schema validation library |
| Docs | README usable; path stale; Phase 0 partially stale on git |
| Dependency pinning | Lower bounds only; no lockfile |

### Evidence vs assumption note

- **FACT:** Journal file under `logs/` with ~168 rows including dry-run/signal events dated 2026-10-27 — supports prior agent dry-run activity.
- **ASSUMPTION:** Those runs used Testnet or Demo; environment at that time not re-proven here.
- **UNVERIFIED:** Current `.env` values, live connectivity, and order acceptance on Bybit.

---

## Backend Readiness

| Capability | Status |
|------------|--------|
| FastAPI app / routers | **Missing** |
| Pydantic API schemas | **Missing** (dataclasses only inside agent) |
| AuthN/AuthZ | **Missing** |
| PostgreSQL / ORM / migrations | **Missing** |
| Background workers / job queue | **Missing** (sync `time.sleep` loop) |
| Read-only market/account API for UI | **Missing** — logic exists in `bot/` but CLI-bound |
| Paper / research data store | **Missing** |
| Health / metrics endpoints | **Missing** |

**Reusable backend seeds:** `create_session`, `call_api`, instrument cache/normalize, `AgentSettings`, `RiskManager.plan_trade`, `TradeJournal` schema, strategy `Signal` model.

**Gap for research MVP API:** Extract pure services from CLI; add FastAPI read endpoints first (balance, positions, last signals, journal tail) with **no** place-order routes until safety gates are hardened.

---

## Frontend Readiness

| Capability | Status |
|------------|--------|
| Next.js / TypeScript app | **Missing** |
| Routing / layout / design system | **Missing** |
| Dashboard components | **Missing** |
| API client / OpenAPI types | **Missing** |
| Auth UI | **Missing** |
| Charts / PnL views | **Missing** |

**Read-only dashboard MVP gap list:**

1. Backend read APIs (equity, positions, open orders, recent journal events, agent status)
2. Next.js app with env-based API base URL
3. Pages: Overview · Positions · Journal · Agent status (dry-run / env label)
4. Explicit banner when mainnet / live-orders mode
5. **No** “Place order” UI in first dashboard MVP

---

## Multi-Agent Readiness

| Planned agent / service | Readiness | Notes |
|-------------------------|-----------|-------|
| Technical Analysis Agent | **Low** | Only EMA/RSI strategy class; no agent protocol |
| SMC Agent | **Missing** | No structure/order-block logic |
| Strategy Coordinator | **Missing** | Runner hardcodes one strategy |
| Independent Risk Engine | **Low** | In-process `RiskManager`; must become fail-closed service |
| Execution Service | **Low** | `OrderExecutor` is a start; needs idempotency + reconcile |
| Portfolio Service | **Missing** | |
| Monitoring | **Missing** | CSV only |

### Recommended contracts (target; not implemented)

```text
MarketSnapshot { symbol, category, candles[], last_price, ts }
SignalProposal {
  agent_id, symbol, action(BUY|SELL|HOLD), confidence[0..1],
  price_ref, rationale, expires_at, bar_close_ts
}
CoordinatorDecision {
  action, size_hint?, reasons[], dissenting[], requires_risk_ack
}
RiskVerdict {
  allow:bool, qty?, tp?, sl?, leverage?,
  reasons[], halt:bool, correlation_id
}
ExecutionIntent {
  client_order_id, symbol, side, qty, order_type,
  reduce_only, tp?, sl?, mode(DRY|PAPER|LIVE)
}
ExecutionReport {
  client_order_id, exchange_order_id?, status,
  filled_qty, avg_price?, error?
}
```

### Module boundaries (recommended)

```text
packages/exchange/     # Bybit REST/WS adapter only (no CLI)
packages/marketdata/   # candles, indicators, bar-close gating
packages/strategies/   # TA, SMC, … → SignalProposal
packages/coordinator/  # votes / priority / conflict rules
packages/risk/         # sole authority to approve size / halt
packages/execution/    # idempotent orders, reconcile, modes
packages/portfolio/    # positions, PnL, exposure
packages/journal/      # immutable event log → DB
apps/api/              # FastAPI
apps/web/              # Next.js read-only then progressive
apps/worker/           # agent loops / consumers
```

Keep **risk and execution** independent of strategy code. Strategies never call `place_order`.

---

## Reusable Components

| Component | Path | Reuse guidance |
|-----------|------|----------------|
| Session factory | `bot/client.py` | Keep; disable retries for non-idempotent orders or always set `orderLinkId` |
| Env flags | `bot/config.py` | Keep; add validated settings object |
| `call_api` | `bot/api.py` | Reuse for read paths; separate write path with idempotency |
| Instrument normalize | `bot/market.py` | Extract to pure exchange helpers (strip CLI prompts) |
| Wallet helpers | `bot/account.py` | Extract non-print functions for API |
| Interactive trading | `bot/trading.py` | Isolate as `cli/` later; do not import into services |
| CLI utils | `bot/utils.py` | CLI-only |
| Agent settings | `agent/config.py` | Promote to shared settings; keep live lock |
| Indicators / candles | `agent/market_data.py` | Split math vs I/O; add confirmed-bar filter |
| EMA/RSI strategy | `agent/strategies/*` | First TA agent implementation |
| Risk planning | `agent/risk.py` | Evolve into Risk Engine; persist halt |
| Executor | `agent/executor.py` | Seed Execution Service |
| Journal schema | `agent/journal.py` | Migrate CSV → Postgres event table |
| Runner | `agent/runner.py` | Temporary orchestrator until coordinator |

**Replace / retire eventually:** print-driven UX inside market/account modules; in-memory-only risk; dry-run-as-paper myth; root ad-hoc CSV artifacts.

---

## Technical Debt

1. **Almost all code untracked** — migration/commit discipline incomplete; high secret-commit risk if ignore stays weak.
2. **`.gitignore` regression** vs prior comprehensive template.
3. **README path drift** (`bybit-trading-bot` vs current folder name).
4. **Fail-open position errors** and **retry without idempotency**.
5. **Forming-candle signals**.
6. **Dry-run increments `open_count`** as if filled (`runner.py`) — skews multi-symbol dry-run behavior.
7. **No lockfile / Python version pin** (Phase 0 noted host 3.11 vs venv 3.13 — **ASSUMPTION** still plausible; not re-measured this audit).
8. **`test_connection.py` naming** implies tests; it is a live network script.
9. **Duplicate journal files** (root vs `logs/`).
10. **PHASE_0 “zero commits”** claim is **STALE DOC**.
11. **No abstraction for paper vs live** — commercial path will need a broker interface.
12. **Strategy hardcoded in runner** — blocks multi-agent without refactor.

---

## Proposed Target Structure

```text
repo/
├── apps/
│   ├── api/                 # FastAPI (read-only first)
│   ├── web/                 # Next.js + TypeScript dashboard
│   └── worker/              # agent/coordinator runtime
├── packages/
│   ├── exchange_bybit/      # REST + later WS
│   ├── domain/              # shared pydantic models / contracts
│   ├── marketdata/
│   ├── strategies_ta/
│   ├── strategies_smc/
│   ├── coordinator/
│   ├── risk_engine/
│   ├── execution/
│   ├── portfolio/
│   └── journal/
├── db/
│   ├── migrations/          # Alembic
│   └── seeds/
├── cli/                     # current main.py UX moved here
├── tests/
│   ├── unit/
│   └── integration/         # mocked exchange only in CI
├── docs/
├── .env.example
├── docker-compose.yml       # api + db (+ web later)
└── README.md
```

Migration approach: **strangle** — keep `bot/`/`agent/` working while extracting libraries; do not big-bang rewrite.

---

## Step-by-Step Implementation Plan

Priority order: **secrets & trading safety → backend API → frontend dashboard → research → multi-agent**.

### Phase 0 — Repository hygiene (immediate)

| | |
|--|--|
| **Objectives** | Restore safe ignores; prevent secret/journal leaks; align docs paths; plan first safe commit (when you request it) |
| **Files** | `.gitignore`, `README.md`, relocate/delete root CSV, optionally `.gitattributes` |
| **Dependencies** | None |
| **Acceptance tests** | `git check-ignore` covers `.env`, `.env.*`, `*.csv` journals, `*.db`, `.venv`; `git status` never shows `.env` |
| **Done when** | Ignore matrix restored; README path correct; root journal not commit-candidate |

### Phase 1 — Trading safety hard gates

| | |
|--|--|
| **Objectives** | Fail-closed positions; idempotent orders; persisted halt; confirmed bars; halt optional flatten policy documented |
| **Files** | `agent/executor.py`, `agent/market_data.py`, `agent/risk.py`, `agent/strategies/ema_rsi.py`, `agent/runner.py`, `bot/client.py` (write-path policy) |
| **Dependencies** | Phase 0 |
| **Acceptance tests** | Unit tests: position error → no new entry; same `orderLinkId` not double-sent; halt file survives restart; strategy ignores in-progress bar |
| **Done when** | Testnet dry-run-off checklist documented; mainnet agent still default-blocked |

### Phase 2 — Offline test harness

| | |
|--|--|
| **Objectives** | Pytest + mocked HTTP; CI workflow; never hit Bybit in CI |
| **Files** | `tests/**`, `.github/workflows/ci.yml`, `requirements-dev.txt` or `pyproject.toml` |
| **Dependencies** | Phase 1 interfaces stable enough to mock |
| **Acceptance tests** | CI green offline; safety lock tests included |
| **Done when** | PR/CI gate exists |

### Phase 3 — Exchange/CLI separation + read API

| | |
|--|--|
| **Objectives** | Extract non-CLI exchange services; FastAPI read-only endpoints (equity, positions, orders, journal, agent status); still **no** public place-order API |
| **Files** | New `apps/api`, `packages/exchange_bybit`, thin wrappers over existing bot helpers |
| **Dependencies** | Phases 0–2 |
| **Acceptance tests** | OpenAPI schema; auth stub or local token; endpoints return fixture/mocked data in tests |
| **Done when** | Dashboard can be built against stable contracts |

### Phase 4 — Read-only Next.js dashboard MVP

| | |
|--|--|
| **Objectives** | Overview, positions, journal, agent mode banner |
| **Files** | `apps/web/**` |
| **Dependencies** | Phase 3 |
| **Acceptance tests** | Desktop/mobile load; shows dry-run/env; no trade buttons |
| **Done when** | Operator can monitor research runs without SSH/CSV only |

### Phase 5 — Research MVP (paper + backtest store)

| | |
|--|--|
| **Objectives** | Paper broker (simulated fills); historical candles store; replay; metrics |
| **Files** | `packages/execution` paper mode; `db/`; research CLI/worker |
| **Dependencies** | Phases 1–3 |
| **Acceptance tests** | Paper run produces journal + equity curve without exchange orders |
| **Done when** | Strategy research possible without Testnet keys |

### Phase 6 — Multi-agent research loop

| | |
|--|--|
| **Objectives** | TA agent + SMC stub + coordinator + risk veto over shared contracts |
| **Files** | `packages/strategies_*`, `packages/coordinator`, worker |
| **Dependencies** | Phase 5 contracts |
| **Acceptance tests** | Conflicting signals → risk deny or single decision; all proposals journaled |
| **Done when** | Multi-agent dry/paper loop demonstrable |

### Phase 7 — Hardened live Testnet automation

| | |
|--|--|
| **Objectives** | Reconciliation, monitoring alerts, emergency cancel/flatten API (authenticated) |
| **Files** | execution reconcile, monitoring, restricted control plane |
| **Dependencies** | Phases 1–6 |
| **Acceptance tests** | Chaos: timeout, duplicate intent, restart mid-halt |
| **Done when** | Documented Testnet live soak passes |

### Phase 8 — Commercial SaaS foundations (later)

| | |
|--|--|
| **Objectives** | Auth, tenancy, encrypted key vault, billing hooks, audit log, rate limits; still default paper/testnet |
| **Files** | api auth, db tenancy, web login |
| **Dependencies** | Proven Testnet automation + security review |
| **Acceptance tests** | No cross-tenant key access; live mainnet requires explicit org policy |
| **Done when** | Security review signed off before any customer mainnet |

---

## Immediate Next 5 Tasks

1. **Restore a production-grade `.gitignore`** — cover `.env*`, journals (`logs/`, `agent_*.csv`, root CSV), DBs, secrets, caches, IDE junk; keep `.env.example` trackable.
2. **Quarantine journal artifacts** — ensure only `logs/` is used; remove or ignore root `agent_20261027.csv`; never stage `.env`.
3. **Implement fail-closed `get_position`** — distinguish `FLAT` vs `UNKNOWN`; skip entries on `UNKNOWN`.
4. **Add agent `orderLinkId` (idempotent client ids)** and stop blindly retrying market `place_order` without dedupe.
5. **Persist daily halt state to disk** (and evaluate on confirmed/closed bars only) before any Testnet `AGENT_DRY_RUN=false` soak.

---

## Appendix A — Defaults cheat sheet (FACT from code / `.env.example`)

| Setting | Default | Role |
|---------|---------|------|
| `BYBIT_TESTNET` | `true` | Testnet endpoint |
| `BYBIT_DEMO` | `false` | Demo overrides testnet when true |
| `AGENT_ENABLED` | `true` | Master switch |
| `AGENT_DRY_RUN` | `true` | No live orders |
| `AGENT_ALLOW_LIVE` | `false` | Mainnet live unlock |
| `AGENT_CATEGORY` | `linear` | `linear` \| `spot` |
| `AGENT_RISK_PCT` | `1.0` (clamped 0.1–5) | Margin budget % |
| `AGENT_DAILY_LOSS_PCT` | `3.0` | In-memory halt threshold |
| `AGENT_LEVERAGE` | `3` (clamped 1–20) | Agent only |

## Appendix B — Distinction reminder

| Claim type | Examples in this report |
|------------|-------------------------|
| **FACT** | File tree, git tracked set, presence/absence of FastAPI/Next, code paths for dry-run/mainnet lock, `.gitignore` diff |
| **UNVERIFIED** | Live Bybit connectivity, order acceptance, fill quality |
| **ASSUMPTION** | Historical journal environment; operator intent for SaaS timeline |
| **STALE DOC** | Phase 0 “zero commits”; README `bybit-trading-bot` path |

---

*End of read-only audit. Only this report file was intended to be created; no trading code was executed and no secrets were disclosed.*
