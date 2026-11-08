# Phase 6A — Gate Summary

## Status: FOUNDATION PASS (mocked) — **STOP before Testnet order submission**

### Implemented

| Area | Status |
|------|--------|
| Trading modes (default SIGNALS_ONLY) | **Done** |
| Mock Bybit Testnet adapter | **Done** |
| Real adapter stub (construction gated; place blocked) | **Done** |
| Independent execution risk engine | **Done** |
| Protective SL/TP verify lifecycle | **Done** |
| Durable local execution intents | **Done** (`data/automation_execution.sqlite3`) |
| Execution pipeline (ack ≠ fill) | **Done** |
| Automation status API + Studio panel | **Done** (controls disarmed) |
| Docs | **Done** |

### Planned / not enabled

| Area | Status |
|------|--------|
| Live Testnet `place_order` | **Blocked** — needs connectivity approval + `TESTNET_ORDER_SUBMISSION_APPROVED` |
| Private order/position WebSocket | Designed, not implemented |
| USDT perpetual auto-exec | **Disabled** (`PERPETUAL_AUTO_EXECUTION_ENABLED`) |
| Mainnet trading path | **Does not exist** |
| Supabase order/fill tables | Design only — no migration/writes |
| SignalPipeline auto-bridge to live orders | Not armed (requests are explicit `SignalExecutionRequest`) |

### Kill switches (defaults)

```
CRYPTONOVA_TRADING_MODE=SIGNALS_ONLY
TESTNET_TRADING_ENABLED=false
TESTNET_TRADING_OPERATOR_APPROVED=false
TESTNET_ORDER_SUBMISSION_APPROVED=false
PERPETUAL_AUTO_EXECUTION_ENABLED=false
MAINNET_TRADING_ENABLED=false
AGENT_ALLOW_LIVE=false   # not used as Testnet shortcut
```

### Testnet connectivity checklist (do not run until approved)

1. Confirm dedicated Testnet API keys (not Mainnet)  
2. `BYBIT_TESTNET=true`, `BYBIT_DEMO=false`  
3. Clock skew patch healthy  
4. Read-only balance/instrument call succeeds on Testnet  
5. Operator sets dual Testnet gates + `TESTNET_ORDER_SUBMISSION_APPROVED`  
6. Spot-only smoke with tiny size + mandatory SL  
7. Reconcile ack/fill/protection before any second order  

### Operator approval checkpoint

Reply explicitly to approve:

1. **Testnet connectivity probe** (reads only)  
2. **Enable order submission gate** for Spot Testnet  
3. **First supervised Spot Testnet order** (tiny notional)  

Until then: no exchange order submission from CryptoNova automation.
