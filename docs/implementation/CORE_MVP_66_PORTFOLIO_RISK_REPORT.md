# CryptoNova — Master Prompt 66 Report

| Field | Value |
| --- | --- |
| Overall status | **COMPLETE** |
| Date | 2026-11-08 |
| Baseline | `main` @ `345d3a1f443ba9af57d5661154c33ae6facb99a7` |

---

## Findings (existing engines)

- Signal risk uses **hypothetical** `paper_balance` (default 10k), ATR stops, RR, cooldown, daily hypothetical halt — not the 65A ledger.
- Paper broker already had count/exposure/cash guards independent of signal risk.
- Gap: no fee-aware portfolio sizing against marked equity; no durable drawdown/daily-loss from reconciled equity.

---

## Delivered

- `reconcile_equity` + valuation statuses
- `PortfolioRiskConfig` + `evaluate_portfolio_entry`
- Fee/slippage-aware sizing + net RR
- Schema v2: `paper_risk_state`, `paper_equity_snapshots` (+ v1 migration)
- Optional `PaperBroker(portfolio_risk=...)` with atomic recheck
- Opt-in `submit_decision_with_portfolio_risk` (veto authoritative)
- Demo: `scripts/demo_portfolio_risk_66.py`
- Tests: `test_core_portfolio_risk.py`, `test_core_paper_risk_integration.py`

---

## Demo highlights (synthetic)

- Candidate A APPROVED with resized qty / net RR ≥ 1.5
- Candidate B oversized request resized under exposure/risk
- Daily-loss halt → new entry `PORTFOLIO_HALTED`
- Restart preserved halt

---

## Safety

Auto-attach OFF · No mutation APIs · No exchange/cloud · Signal pipeline unchanged · `execution_allowed` preserved
