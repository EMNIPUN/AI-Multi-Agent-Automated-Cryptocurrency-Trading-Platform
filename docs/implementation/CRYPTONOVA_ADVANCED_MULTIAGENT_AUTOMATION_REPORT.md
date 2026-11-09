# CryptoNova — Advanced Multi-Agent Automation (PAPER → TESTNET)

**Status:** Implemented for PAPER control plane + gated TESTNET bridge. LIVE remains blocked. LLM/news remain advisory.

## Locked decisions

- Hybrid richer agents + offline calibration; LLM/news cannot change BUY/SELL.
- Finish advanced PAPER, then unlock TESTNET lifecycle behind dual env gates.
- Evolve `SignalPipeline` spine — do not revive `AgentRunner` as the product path.

## Phase deliverables

| Phase | Item | Status |
| --- | --- | --- |
| 1 | Volume + structure agents, `STRATEGY_VERSION=6.0.0` | DONE |
| 1 | Offline `CalibrationProfile` fit/apply + before/after metrics | DONE |
| 2 | Autonomy contract (`/autonomy`, `/decisions`, `/agents/runtime`, `/risk`) | DONE |
| 2 | Decision queue, protective closes, per-agent runtime honesty | DONE |
| 3 | Dashboard fleet overview, shared `lib/agents/registry.ts`, Risk Center feed, GlobalStatusBar mode strip | DONE |
| 4 | `decision_bridge` → `ExecutionPermissionGateway` → PAPER/TESTNET | DONE |
| 4 | Real Bybit testnet adapter HTTP (gated) + reconcile (no blind resubmit) | DONE |
| 5 | Unit coverage + this report; LIVE denied | DONE |

## Runtime architecture

```text
SignalPipeline (market, trend, momentum, volume, structure, regime, risk)
  → CoordinatorDecision (execution_allowed=False)
  → PaperSupervisor (PAPER auto place/track/close)
  → decision_bridge / ExecutionPermissionGateway
       PAPER → paper broker (unchanged)
       TESTNET → AutomatedExecutionPipeline (dual gates)
       LIVE → Denied
```

## Operator notes

- Primary ops desk: `/autonomy`
- Scores are calibrated historical agreement — not guaranteed win probability.
- Arm TESTNET only via env (`CRYPTONOVA_TRADING_MODE=TESTNET_TRADING` + dual approvals + `TESTNET_ORDER_SUBMISSION_APPROVED`). Chat/HTTP cannot arm alone.
- LIVE mainnet orders stay locked.

## Key files

- `agent/multi_agent/volume_agent.py`, `structure_agent.py`, `calibration.py`
- `agent/supervisor/autonomy_contract.py`
- `agent/automation/decision_bridge.py`, `reconcile.py`, `testnet_adapter.py`
- `apps/web/src/lib/agents/registry.ts`
- `tests/test_advanced_agents_calibration.py`, `test_autonomy_contract.py`, `test_decision_bridge_testnet_lifecycle.py`

## Worker ownership

Long-running paper supervisor remains API-hosted (`apps/api` runtime). TESTNET reconcile is available as a library path (`agent/automation/reconcile.py`) for the future `apps/worker` cutover — interim ownership stays with API/automation until a dedicated worker process is promoted.
