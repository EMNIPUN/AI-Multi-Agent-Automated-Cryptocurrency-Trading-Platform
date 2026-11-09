# AI Multi-Agent Automated Cryptocurrency Trading Platform

Research-first trading platform built around Bybit. The **product path** is CryptoNova’s multi-agent `SignalPipeline` (market → trend → momentum → volume → structure → regime → risk) with autonomous **PAPER** place/track/close via the paper supervisor, FastAPI + Next.js ops desk (`/autonomy`), and a gated **TESTNET** execution bridge. **LIVE** mainnet orders stay locked. A legacy terminal + EMA/RSI `run_agent.py` path remains for research.

## Features

### Manual terminal (`main.py`)
- Spot & futures market data (ticker, order book, candles)
- Unified account balance
- Spot market / limit buy & sell
- Futures long / short, leverage, close position, optional TP/SL
- Open orders, cancel one / cancel all
- Qty & price rounded to exchange filters
- Confirmation before every order

### Automated agent (`run_agent.py`)
- EMA fast/slow crossover + RSI filter
- Dry-run by default (no orders)
- Risk: equity %, max positions, daily loss kill switch, TP/SL on futures
- CSV journal under `logs/`
- Mainnet live orders blocked unless `AGENT_ALLOW_LIVE=true`

## Setup

Preferred (locked deps via `uv.lock`):

```powershell
cd "E:\Financial Side\Trading\AI-Multi-Agent-Automated-Cryptocurrency-Trading-Platform"
uv sync --group dev
copy .env.example .env
```

Fallback without `uv`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
```

Edit `.env` with your API key/secret. Never put database passwords or Supabase service-role keys in Next.js `NEXT_PUBLIC_*` variables.

### Read-only FastAPI (Phase 2A)

```powershell
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

- `GET /health` — liveness (no secrets / no Bybit)
- `GET /api/v1/system/status` — safe status metadata

PostgreSQL/Supabase is optional for those routes. Migrations are **manual** (`apps/api/alembic`); see `apps/api/README.md`.

| Setting | Meaning |
|---|---|
| `BYBIT_TESTNET=true` | Testnet (`api-testnet.bybit.com`) — recommended |
| `BYBIT_TESTNET=false` | Live mainnet — real money |
| `BYBIT_DEMO=true` | Demo Trading (`api-demo.bybit.com`) |

API keys are **not interchangeable** across testnet / mainnet / demo.  
Create keys with **Read + Trade** (no withdrawal needed).

## Run manual trader

```powershell
python test_connection.py
python main.py
```

## Run automated agent

Recommended path:

1. **Testnet + dry-run** (signals only)
2. **Testnet + dry-run off** (real testnet orders)
3. Optional **mainnet** only with `AGENT_ALLOW_LIVE=true` after proven results

```powershell
# 1) Dry-run (default)
# AGENT_DRY_RUN=true
python run_agent.py

# 2) Testnet live agent orders
# BYBIT_TESTNET=true
# AGENT_DRY_RUN=false
# AGENT_ALLOW_LIVE=false   # not needed on testnet
python run_agent.py

# 3) Mainnet live (dangerous)
# BYBIT_TESTNET=false
# AGENT_DRY_RUN=false
# AGENT_ALLOW_LIVE=true
python run_agent.py
```

Useful agent settings (see `.env.example`):

| Setting | Default | Meaning |
|---|---|---|
| `AGENT_ENABLED` | true | Master switch |
| `AGENT_DRY_RUN` | true | Log only, no orders |
| `AGENT_ALLOW_LIVE` | false | Required for mainnet real orders |
| `AGENT_CATEGORY` | linear | `linear` or `spot` |
| `AGENT_SYMBOLS` | HYPEUSDT | Comma-separated symbols |
| `AGENT_INTERVAL` | 15 | Kline minutes |
| `AGENT_POLL_SECONDS` | 60 | Loop delay |
| `AGENT_RISK_PCT` | 1.0 | % equity (margin budget) per new trade |
| `AGENT_LEVERAGE` | 3 | Futures leverage |
| `AGENT_DAILY_LOSS_PCT` | 3.0 | Kill switch vs day-start equity |
| `AGENT_TP_PCT` / `AGENT_SL_PCT` | 1.5 / 1.0 | Futures take-profit / stop-loss |

Logs: `logs/agent_YYYYMMDD.csv`

## Manual menu map

1. Spot market data  
2. Futures market data  
3. Account balance  
4. Futures positions  
5. Spot trading  
6. Futures trading  

## Safety

- Prefer **testnet** or **demo** until you are comfortable.
- Agent defaults to **dry-run**; mainnet needs an extra live flag.
- Small accounts cannot trade large min-size perps (e.g. BTCUSDT `0.001`).
- Manual mainnet orders require typing `yes`.
- Futures use one-way mode (`positionIdx=0`).
- Trading involves risk; use at your own responsibility. No profit is guaranteed.

## Project layout

Current trading code (unchanged entry points):

```
main.py              # manual terminal menus
run_agent.py         # automated agent entry
test_connection.py   # auth check (not a unit test)
bot/                 # shared Bybit helpers + CLI trading
agent/
  config.py          # agent .env settings
  market_data.py     # candles + indicators
  strategies/        # EMA+RSI strategy
  risk.py            # sizing + kill switch
  executor.py        # dry-run / place orders
  journal.py         # CSV logs
  runner.py          # main loop
tests/               # offline mocked unit tests
```

Monorepo scaffolding (structure only; apps not implemented yet):

```
apps/api/            # future FastAPI
apps/web/            # future Next.js + TypeScript
apps/worker/         # future agent/job workers
packages/            # future shared libraries
research/            # offline research / backtests
docs/architecture/   # structure & design docs
docs/implementation/ # phase / restructure reports
docs/audits/         # audit index
scripts/             # dev helpers
infra/               # future compose / CI / deploy
```

See `docs/architecture/REPOSITORY_STRUCTURE.md` for current vs future migration notes.
