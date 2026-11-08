# Phase 6A — Execution Risk Controls

Independent from Phase 4 paper `SignalRiskState`.

## Hard limits (defaults)

| Control | Default |
|---------|---------|
| Max risk / trade | 0.5% equity |
| Max daily loss | 2% equity |
| Max concurrent positions | 1 |
| Max portfolio exposure | 25% equity |
| Max position notional | 500 USDT |
| Min available balance | 50 USDT |
| Max spread | 15 bps |
| Max data age | 120s |
| Max API errors / hour window | 10 |
| Stop-loss required | yes |
| Spot-only default | yes |

## Halts

- Daily loss → `HALTED`
- Protection unverified / stop rejected → emergency halt, no new entries
- Excessive API errors → veto
- Duplicate `client_order_id` → veto
- Unexpected open exposure counted via concurrent/notional caps

## Futures (designed, disabled)

`PERPETUAL_AUTO_EXECUTION_ENABLED=false` until approved. Future checks: leverage, margin, liquidation buffer, funding.

## Modes vs legacy flags

| Flag | Role |
|------|------|
| `CRYPTONOVA_TRADING_MODE` | Primary mode |
| `TESTNET_TRADING_ENABLED` + `_OPERATOR_APPROVED` | Arm Testnet mode |
| `TESTNET_ORDER_SUBMISSION_APPROVED` | Allow `place_order` |
| `AGENT_ALLOW_LIVE` | **Not** used as Testnet/Mainnet shortcut |
| `MAINNET_TRADING_ENABLED` | Must stay false; no execution path |
