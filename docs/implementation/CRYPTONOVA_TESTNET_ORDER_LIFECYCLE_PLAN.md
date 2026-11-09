# CryptoNova — Bybit Testnet Order Lifecycle Plan

**Status:** Prepared. No testnet orders are authorized by this document.

## Preconditions (all required)

1. `BYBIT_TESTNET=true`, `BYBIT_DEMO=false`, `MAINNET_TRADING_ENABLED=false`
2. `TESTNET_TRADING_ENABLED=true`
3. `TESTNET_TRADING_OPERATOR_APPROVED=true`
4. `TESTNET_ORDER_SUBMISSION_APPROVED=true` (separate approval)
5. Read-only connectivity preparation passed
6. Dedicated testnet credentials with trade permission only (no withdraw)
7. Isolated testnet journal / labels — never mixed with PAPER or LIVE

## Lifecycle cases to execute after approval

| # | Case | Expectation |
| --- | --- | --- |
| 1 | Authenticated instrument metadata for HYPEUSDT | min qty / step / notional match exchange |
| 2 | Entry order submit | ack with durable client order id |
| 3 | Partial fill | position and remaining qty reconcile |
| 4 | Full fill | open position matches exchange |
| 5 | Protective stop-loss | exchange-confirmed protective order |
| 6 | Take-profit | exchange-confirmed protective order |
| 7 | Cancel open order | cancel confirmed before new exposure |
| 8 | Unknown ack / timeout | no blind resubmit; block new exposure |
| 9 | Restart with open position | recover from journal + exchange evidence |
| 10 | Emergency halt | block new entries; allow protective exits only |
| 11 | Auth failure | fail closed; no orders |
| 12 | Wrong environment label | refuse; never continue |

## Explicit non-goals until approval

- Placing any testnet order
- Promoting TESTNET to LIVE
- Using mainnet credentials
- Inferring approval from chat or this plan

## Evidence required before marking COMPLETE AND VERIFIED

- Request/response ids (redacted)
- Order link ids
- Fill and position snapshots
- Halt and restart transcripts
- Test suite covering injected success and failure modes
