# CryptoNova Orchestrator V2 Implementation Report

## Summary

Orchestrator V2 delivers a bounded Responses tool loop, mode-scoped OpenAI schemas, local SQLite conversation memory, atomic spend reservation, paper session explanations, and UI surfaces for history / traces / model spend / decision inspection. Live trading remains disarmed by default; CI and eval suites stay mocked with no paid OpenAI requirement.

## Delivered phases

### Phase A — Correctness and security

- `tool_registry.py`: classifies tools; `schemas_for(mode, live_armed)` filters OpenAI visibility.
- `tool_loop.py`: create → function calls → validate/execute → `function_call_output` with `call_id` → synthesis; caps on rounds, tools, duration.
- `budget.py` + hardened `usage_ledger.py`: `try_reserve` / `commit_reservation` / `release_reservation` under `BEGIN IMMEDIATE`.
- Empty live `proposal_id` refused inside the tool loop (not authority to approve latest).
- PAPER never exposes live mutation schemas to OpenAI.

### Phase B — Intelligent orchestration

- `intent_router.py`: LocalPlanner-confident routes vs OpenAI synthesis.
- `conversation_store.py`: threads, messages, context, reset, TTL-style summarization.
- Chat API: optional `conversation_id` in / out; `GET/POST` conversation helpers.
- `result_contracts.py`: verified facts vs `model_commentary`.
- Telemetry fields: `orchestration_mode`, `model`, `used_fallback`, `fallback_reason`, `result_envelopes`.

### Phase C — Paper coordination

- Session-authorized paper controls (start/pause/resume/halt) unchanged in supervisor.
- “Explain last decision” / HOLD blockers route to `supervisor_status` with decision inspector payload.
- Orchestrator does not invent paper fills from model opinion.

### Phase D — UI

- Persist/load `conversation_id` (localStorage + server history).
- Model & spend panel from `/api/orchestrator/diagnostics` / openai usage.
- Tool trace + decision inspector card.
- LIVE Approve path preserved when armed.

## Evaluation

- Suite: `tests/test_orchestrator_v2_eval.py` (≥60 mocked cases across conversation, analysis, multi-turn, paper controls, risk/stale, budget concurrency, injection, unauthorized live, duplicate tools, tool-loop `call_id`).
- Phase A focused tests: `tests/test_orchestrator_v2_phase_a.py`.
- Regression: orchestrator + supervisor related pytest modules (see counts in report footer after CI/local run).

## Explicit non-claims

- No Bybit mainnet/testnet order submission enabled in this milestone.
- No profitability claims from tests.
- No new Supabase tables.
- No unbounded paid OpenAI evaluation.

## Key env gates

| Variable | Role |
|---|---|
| `ORCHESTRATOR_OPENAI_ENABLED` | Feature gate |
| `ORCHESTRATOR_OPENAI_SPEND_APPROVED` | Spend approval gate |
| `OPENAI_API_KEY` / `CRYPTONOVA_ORCHESTRATOR_MODEL` | Model access |
| `CRYPTONOVA_ORCHESTRATOR_*_BUDGET_USD` | Daily / monthly / total caps |
| `AGENT_ALLOW_LIVE` / `MAINNET_TRADING_ENABLED` | Live arming (default false) |

## Regression counts

Local run (2026-11-09):

| Suite | Result |
|---|---|
| `tests/test_orchestrator_v2_phase_a.py` + `tests/test_orchestrator_v2_eval.py` | **78 passed** |
| Core orchestrator set (`test_core_orchestrator*`, futures intake, live readiness/bridge) | **119 passed** |
| `pytest -k "orchestrator or supervisor or paper_supervisor"` | **128 passed**, **1 failed** (pre-existing: `test_supervisor_lifecycle.py::test_daily_loss_halts_new_entries` — `PaperStore.update_session_balances` unexpected kwarg `realized`; unrelated to Orchestrator V2) |

Paid OpenAI smoke was **not** run. `AGENT_ALLOW_LIVE` remained false in tests.
