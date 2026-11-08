# CryptoNova — Master Prompt 65A Report

| Field | Value |
| --- | --- |
| Overall status | **COMPLETE** (backend broker + tests + demo + docs) |
| Date | 2026-11-08 |
| Repository baseline | `main` @ `345d3a1f443ba9af57d5661154c33ae6facb99a7` |
| Scope note | Milestone 1A only — API/Studio integration deferred (full M1 still PARTIAL) |

---

## Architecture

```
Approved PaperSignalInput / CoordinatorDecision (opt-in adapter)
        │
        ▼
   PaperBroker.submit_signal  →  paper_orders (PENDING|REJECTED)
        │
        ▼
   process_candle (confirmed OHLC)
        │
        ├─ next-bar open + adverse slip → fill → paper_fills + paper_positions
        ├─ mark-to-market
        └─ SL/TP or signal SELL → close → realized PnL + balance
        │
        ▼
   data/*paper*.sqlite3  (separate from signal history v4)
```

Package: `agent/paper/` — `config`, `models`, `accounting`, `fills`, `positions`, `store`, `broker`, `integration`.

Independent of Phase 6A exchange adapters. `PAPER_BROKER_AUTO_ATTACH = False`.

---

## Data models / schema

Tables: `paper_sessions`, `paper_orders`, `paper_fills`, `paper_positions`, `paper_account_events`, `paper_candle_cursor`, `paper_processed_events`, `paper_meta` (schema_version=1).

FK + uniqueness + `BEGIN IMMEDIATE` transactions. Default path suggestion: `data/cryptonova_paper.sqlite3`.

---

## Synthetic demo evidence

Command: `python scripts/demo_paper_broker_65a.py`

| Field | Value |
| --- | --- |
| Session ID | `demo_ps_65a` |
| Starting balance | 1000 USDT |
| Signal ID | `demo_sig_btc_buy_1` |
| Fill price | 50025 (50 000 + 5 bps) |
| Quantity | 0.004 |
| Exit reason | TAKE_PROFIT |
| Exit price | 51974 (52 000 − 5 bps) |
| Gross PnL | 7.796 |
| Fees | 0.407996 |
| Net PnL | 7.388004 |
| Ending balance | 1007.388004 USDT |

Synthetic only — not live performance.

---

## Test evidence

```
.\.venv\Scripts\pytest.exe tests/test_core_paper_broker.py \
  tests/test_core_paper_store.py tests/test_core_paper_integration.py -q
→ 35 passed
```

Coverage includes: session init, BUY/HOLD/BLOCKED/VETO, funds/qty guards, slippage/fees, open/MTM/TP/SL/collision/gap, PnL/balance, max positions/exposure, duplicate signal/fill/exit, restart, rollback, out-of-order/missing candle, no look-ahead, no Bybit private / cloud / OpenAI imports, SELL closes long only.

---

## Limitations / known gaps

- No FastAPI or Studio surfaces (65B+).
- No automatic pipeline attach.
- Spot longs only; no shorts/margin/funding/leverage/partial fills.
- OHLC same-bar SL-before-TP bias.
- Synthetic fee/slip defaults ≠ verified Bybit tiers.
- Signal risk agent’s hypothetical `paper_balance` not reconciled to this ledger yet.
- Entry candle can also evaluate SL/TP after fill on the same bar (documented conservative behavior).

---

## Safety confirmation

| Check | Result |
| --- | --- |
| Exchange orders | NONE |
| Bybit private order APIs | NOT CALLED |
| Remote DB mutations | NONE |
| Cloud writes/sync | OFF |
| Gate 63 | NOT EXECUTED |
| OpenAI | NONE |
| Deploy / git push | NONE |
| `execution_allowed` semantics | PRESERVED |
| Auto-attach | OFF |

---

## Next recommended milestone

**65B** — opt-in FastAPI paper session/order read APIs + explicit Studio wiring; keep default OFF. Then Milestone 2 risk hardening against reconciled paper equity.
