# Phase 6A — Order Lifecycle

## States (execution intent store)

`CREATED` → `SUBMISSION_PENDING` → `ACCEPTED` (ack only) → `FILLED` (exchange-proven)  
Also: `PAPER_SIMULATED`, `BLOCKED_BY_GATE`, `RISK_BLOCKED`, `RECONCILIATION_REQUIRED`, `UNKNOWN`, `MAINNET_LOCKED`, `LINEAR_DISABLED`, `SIGNALS_ONLY`

## Ack vs fill

`OrderAck` means the exchange accepted the request. **Not** a fill.  
Fills require execution evidence (mock `simulate_full_fill` in tests; live reconcile later).

## Protective lifecycle

1. Valid SL required before risk approval  
2. After proven fill → `set_trading_stop`  
3. Re-read position; require visible stop  
4. If reject/missing → `protection_unverified` + emergency halt  
5. Never assume cancel/close without confirmation  

## Emergency procedure (documented)

- Halt new entries  
- Assume nothing cancelled  
- Reconcile open orders/positions  
- Manual operator review  
- Reduce-only flatten only after proven size + Testnet approval  

## Idempotency

`client_order_id` derived from `decision_id|symbol|side|category|strategy_version`.  
Duplicate inserts short-circuit. Mock adapter replays ack for same link id.

## Restart

Local SQLite `automation_execution.sqlite3` retains intents; restart does not resubmit.
