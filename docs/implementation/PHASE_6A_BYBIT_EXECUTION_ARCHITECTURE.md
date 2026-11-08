# Phase 6A — Bybit Execution Architecture

## Goal

Testnet-first automated execution **foundation**. Default mode `SIGNALS_ONLY`. No Mainnet path. No live Testnet orders until explicit submission approval.

## Audit reuse

| Reuse | Path |
|-------|------|
| Idempotent intents / ack≠fill | `agent/executor.py`, `agent/intent_store.py`, `agent/reconcile.py` |
| Live account risk patterns | `agent/risk.py`, `agent/risk_store.py` |
| Write session (no blind retry) | `bot/client.py` `create_write_session` |
| Clock skew | `apps/api/app/exchange/bybit_clock.py` |

| Do not reuse as trading | Why |
|-------------------------|-----|
| `BybitTestnetVerificationAdapter` | Credential verify only |
| SignalPipeline `execution_allowed` | Remains `False`; bridge is separate |
| `AGENT_ALLOW_LIVE` | Not a Testnet/Mainnet shortcut |

## New components

| Module | Role |
|--------|------|
| `agent/automation/modes.py` | SIGNALS_ONLY / PAPER / TESTNET / MAINNET(locked) |
| `agent/automation/testnet_adapter.py` | Protocol + Mock + Real stub (blocked) |
| `agent/automation/execution_risk.py` | Independent hard limits |
| `agent/automation/protective.py` | SL/TP verify after fill |
| `agent/automation/pipeline.py` | Signal request → intent → gated submit |
| `agent/automation/exec_store.py` | Local SQLite execution intents |
| `apps/api/app/automation/router.py` | Status + refused arm endpoint |
| Studio `AutomationControlPanel` | Read-only control plane |

## Pipeline

```
SignalExecutionRequest
  → mode gate (SIGNALS_ONLY skip / MAINNET lock / linear disable)
  → ExecutionRiskEngine
  → durable execution_intent (SQLite)
  → PAPER simulate OR TESTNET place (gated)
  → OrderAck ≠ fill
  → optional mock fill + protective verify
  → emergency halt if protection missing
```

## Environments

- Testnet credentials/endpoints only for Real adapter construction
- Mainnet write client construction refused
- Public market WS remains separate (mainnet public data is OK for signals)

## Supabase

Execution tables **designed only** — no unapproved migrations/writes.
Local exec store is SoT for safety. Cloud outage must not bypass local gates.
