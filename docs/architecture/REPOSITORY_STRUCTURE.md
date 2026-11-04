# Repository Structure

| Field | Value |
|-------|-------|
| Updated | 2026-11-04 |
| Scope | Structure preparation (scaffolding + documentation) |
| Status | `bot/` + `agent/` remain the live trading codepaths |

---

## Purpose

This monorepo is prepared to host:

- FastAPI backend (`apps/api`)
- Next.js + TypeScript frontend (`apps/web`)
- Long-running workers (`apps/worker`)
- Shared Python packages (`packages/`)
- Research / backtesting workspace (`research/`)
- Offline tests, docs, scripts, and infra

**Today**, production trading behavior still lives in root CLI entry points plus `bot/` and `agent/`. `apps/api` has a Phase 2A read-only FastAPI foundation (no trading routes). `apps/web` and `apps/worker` remain scaffolding.

---

## Current layout (authoritative runtime)

```text
AI-Multi-Agent-Automated-Cryptocurrency-Trading-Platform/
├── main.py                 # Manual trading CLI (keep compatible)
├── run_agent.py            # Automated agent entry (keep compatible)
├── test_connection.py      # Authenticated connectivity probe (NOT a unit test)
├── requirements.txt
├── requirements-dev.txt    # pytest, etc. (dev only)
├── .env.example            # Trackable template (no real secrets)
├── bot/                    # Bybit helpers + interactive trading UX
├── agent/                  # EMA/RSI loop: config, risk, executor, journal, runner
├── tests/                  # Offline mocked unit tests
├── docs/                   # Audits, architecture, implementation notes
├── apps/                   # Future deployable applications (scaffolding)
├── packages/               # Future shared libraries (scaffolding)
├── research/               # Offline research workspace (scaffolding)
├── scripts/                # Dev/ops helpers (scaffolding)
└── infra/                  # Compose/CI/deploy stubs (scaffolding)
```

### Python import model (current)

| Pattern | Example | Assumption |
|---------|---------|------------|
| Absolute package imports | `from bot.client import create_session` | Repo root is on `PYTHONPATH` / cwd when running scripts |
| Absolute package imports | `from agent.runner import AgentRunner` | Same |
| Agent → bot dependency | `agent.config` → `bot.config`; `agent.risk` → `bot.market` | `bot` is the exchange/CLI substrate |
| Entry scripts | `main.py`, `run_agent.py`, `test_connection.py` | Run from repository root |

**Do not relocate `bot/` or `agent/` without a planned import migration and test pass.**

### Entry points that must remain compatible

| Entry | Role | Network |
|-------|------|---------|
| `python main.py` | Interactive spot/futures CLI | Authenticated REST if credentials present |
| `python run_agent.py` | Agent poll loop | Authenticated REST if credentials present |
| `python test_connection.py` | Auth/connectivity probe | Authenticated REST |

Safety defaults (must be preserved during migrations):

- `AGENT_DRY_RUN=true` by default
- Mainnet live agent orders require `AGENT_ALLOW_LIVE=true`
- Prefer Testnet / Demo for development

---

## Future layout (target)

```text
apps/
  api/          # FastAPI — read APIs first; no place-order routes early
  web/          # Next.js dashboard — read-only MVP first
  worker/       # Agent/coordinator/job runners
packages/       # Extracted libraries, e.g.:
                #   exchange_bybit, domain, marketdata,
                #   strategies_ta, strategies_smc,
                #   coordinator, risk_engine, execution,
                #   portfolio, journal
research/       # Backtests, notebooks, experiment notes
tests/          # Continues as the offline test root (expand in place)
docs/
  audits/       # Audit index (+ future audits)
  architecture/ # Structure & design docs
  implementation/ # Phase / restructure reports
scripts/        # Offline tooling
infra/          # Docker, local DB, CI helpers
```

Feature package folders under `packages/` are **intentionally not pre-created** empty. Add them when code is extracted with tests.

---

## Migration strategy (strangler)

Gradual extraction — keep CLIs working at every step:

1. **Stabilize safety** in `agent/` / `bot/` (fail-closed positions, idempotent orders, persisted halt, confirmed bars).
2. **Extract pure helpers** (normalize qty/price, indicators, settings) into `packages/*` with re-exports from `bot`/`agent` so imports stay stable.
3. **Introduce `apps/api`** read-only endpoints wrapping extracted services (no execution routes).
4. **Introduce `apps/web`** against those read APIs.
5. **Move loop runtime** into `apps/worker` while `run_agent.py` becomes a thin wrapper.
6. **Add SMC / TA / coordinator** as separate packages behind shared contracts; risk remains the sole authority to approve size.
7. Only later: authenticated control-plane actions, paper broker, SaaS tenancy.

Optional later: move `bot/` + `agent/` under `legacy/` **after** wrappers and tests prove parity — not now.

---

## Documentation map

| Kind | Where |
|------|-------|
| Structure (this file) | `docs/architecture/REPOSITORY_STRUCTURE.md` |
| Restructure report | `docs/implementation/RESTRUCTURE_REPORT.md` |
| Audit index | `docs/audits/README.md` |
| Repository audit | `CURRENT_REPOSITORY_AUDIT.md` (root, unchanged path) |
| Phase safety reports | `docs/PHASE_0_*.md`, `docs/PHASE_1A_*.md` |

Audit markdown was **not moved**, so existing relative references stay valid.

---

## Explicit non-goals of this structure pass

- No FastAPI / Next.js initialization
- No new trading features or strategy changes
- No order-execution HTTP endpoints
- No live trading enablement
- No second virtualenv / dependency installs as part of scaffolding
