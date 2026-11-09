# apps/worker

Long-running **worker** process(es) for agent loops, coordinators, and background jobs.

## Current ownership (interim)

- **PAPER autonomous supervisor** ticks run inside `apps/api` via `PaperSupervisorWorker` (`apps/api/app/orchestrator/runtime.py`) when `CRYPTONOVA_PAPER_SUPERVISOR=true`.
- **TESTNET reconcile** helpers live in `agent/automation/reconcile.py` and are invoked from the automation API / gated pipeline — not yet a standalone worker binary.
- Legacy `run_agent.py` remains a separate EMA/RSI path and is **not** the CryptoNova multi-agent product spine.

## Target cutover

Promote paper supervisor + TESTNET reconcile into this package while preserving:

- dry-run / PAPER defaults
- dual TESTNET env gates
- LIVE mainnet locks (`AGENT_ALLOW_LIVE` + denied live adapter)
- no chat unlock of execution mode
