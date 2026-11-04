# Restructure Report — Monorepo Scaffolding

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Type | Structure preparation only |
| Constraints | No trading-logic edits for this task; no FastAPI/Next init; no installs; no stage/commit/push; no live exchange scripts |

---

## Summary

Created professional monorepo scaffolding (`apps/*`, `packages/`, `research/`, `scripts/`, `infra/`, expanded `docs/`) while leaving `bot/`, `agent/`, and root CLI entry points in place with unchanged import paths.

Existing audit documents were **not moved** (cross-references preserved). An index was added at `docs/audits/README.md`.

---

## Task 1 — Inspection findings

### Import / dependency model

- All application modules use **absolute** imports (`bot.*`, `agent.*`).
- No relative `from ..` package imports in trading code.
- Runtime assumption: process cwd / `PYTHONPATH` includes **repository root**.
- Dependency direction: `agent` → `bot` (config, market normalize, utils); entry scripts → both.
- `tests/` imports `agent.*` and `tests.conftest` the same way (repo-root based).

### Entry points (must stay compatible)

| File | Notes |
|------|-------|
| `main.py` | Manual CLI |
| `run_agent.py` | Agent loop |
| `test_connection.py` | Authenticated probe — not a unit test |

### Working tree note (at inspection)

Unrelated prior Phase 1A work may appear as modified `agent/market_data.py`, `agent/risk.py`, `agent/runner.py` plus `tests/` and `docs/PHASE_1A_POSITION_SAFETY_REPORT.md`. **This restructure task did not modify those trading files.** Reviewers should treat Phase 1A diffs separately from scaffolding.

### Git hygiene (verified offline)

- `.env` ignored; `.env.example` trackable
- Journals / DBs / `.venv` / Node build artifacts covered by existing `.gitignore`
- No secret files tracked

---

## Files created

| Path | Purpose |
|------|---------|
| `apps/api/README.md` | FastAPI app placeholder |
| `apps/web/README.md` | Next.js app placeholder |
| `apps/worker/README.md` | Worker app placeholder |
| `packages/README.md` | Shared packages policy |
| `research/README.md` | Research workspace |
| `scripts/README.md` | Dev/ops scripts |
| `infra/README.md` | Infra stubs |
| `tests/README.md` | Offline test guidance |
| `docs/audits/README.md` | Audit index (no file moves) |
| `docs/architecture/REPOSITORY_STRUCTURE.md` | Current vs future structure |
| `docs/implementation/RESTRUCTURE_REPORT.md` | This report |

## Files moved

None.

## Files modified

| Path | Change |
|------|--------|
| `README.md` | Project layout section updated to mention monorepo scaffolding; entry points unchanged |

## Files intentionally not modified

- `bot/**` (trading/exchange helpers)
- `agent/**` (strategy/risk/execution/runner)
- `main.py`, `run_agent.py`, `test_connection.py`
- `bot/client.py` / env loading
- `.env`, journal CSVs
- Dry-run / mainnet live-lock defaults

---

## Verification performed

| Check | Result |
|-------|--------|
| AST syntax parse of `bot/`, `agent/`, root entry scripts | **Pass** (`SYNTAX_OK`) |
| Import `bot.*` / `agent.*` packages without running CLI entry scripts | **Pass** (`IMPORT_OK`) |
| Import paths for `bot` / `agent` unchanged | Pass (no moves) |
| Trading source edited by **this** scaffolding task | None — existing `agent/*.py` diffs are prior Phase 1A work |
| Secrets staged/tracked | `.env` not tracked; ignored |
| `.env.example` trackable | Pass |
| Bybit network / orders | Not executed |
| Next.js / FastAPI initialized | No |
| Dependencies installed for this task | No |
| `pytest` | Not re-run in this pass; suite exists under `tests/` from Phase 1A and can be run offline separately |

### Tests that cannot yet be executed (by design of this pass)

- Live exchange / authenticated connectivity (`test_connection.py`, `main.py`, `run_agent.py`) — **must not** be run for structure verification
- FastAPI / frontend e2e — apps not initialized
- Backtests / SMC / multi-agent suites — not implemented

---

## Acceptance criteria

| Criterion | Status |
|-----------|--------|
| Existing trading functionality preserved by design | Pass |
| Original Python entry points remain in place | Pass |
| No Bybit network calls or orders | Pass |
| No real API credentials exposed | Pass |
| No application trading logic changes (this task) | Pass |
| New folders organized and documented | Pass |
| Changes left unstaged/uncommitted for review | Pass (operator responsibility; this task does not stage/commit) |

---

## Recommended next development task

**Phase 1B — Agent order idempotency:** add stable `orderLinkId` on agent placements and tighten retry behavior for non-idempotent market IOC orders (`CURRENT_REPOSITORY_AUDIT.md` / Phase 1A recommended next step).

After safety hard gates: extract read-only services and bootstrap `apps/api` without execution routes.
