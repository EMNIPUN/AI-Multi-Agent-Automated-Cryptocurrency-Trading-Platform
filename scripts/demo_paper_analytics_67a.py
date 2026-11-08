#!/usr/bin/env python3
"""Synthetic paper analytics demonstration (Prompt 67A). Not live performance."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.paper.analytics.service import compute_session_analytics
from agent.paper.read_store import PaperReadStore
from tests.helpers_paper_analytics_seed import seed_mixed_session


def main() -> int:
    db = ROOT / "data" / "demo_cryptonova_paper_67a.sqlite3"
    if db.exists():
        db.unlink()
    sid = seed_mixed_session(db, session_id="demo_ps_67a")
    a = compute_session_analytics(PaperReadStore(db), sid)

    print("=== CryptoNova Paper Analytics Demo 67A (SYNTHETIC) ===")
    print(f"Session:           {a.session_id}")
    print(f"Closed trades:     {a.closed_trades}")
    print(f"Open positions:    {a.open_positions}")
    print(f"W/L/BE:            {a.winning_trades}/{a.losing_trades}/{a.breakeven_trades}")
    print(f"Win rate:          {a.win_rate_pct.value} ({a.win_rate_pct.status.value})")
    print(f"Gross profit:      {a.gross_profit}")
    print(f"Gross loss:        {a.gross_loss}")
    print(f"Net PnL:           {a.net_realized_pnl}")
    print(
        f"Profit factor:     {a.profit_factor.value} ({a.profit_factor.status.value}"
        f"{f' / {a.profit_factor.reason}' if a.profit_factor.reason else ''})"
    )
    print(f"Expectancy:        {a.expectancy.value}")
    print(f"Fees:              {a.total_fees}")
    print(f"Return % (init):   {a.realized_return_pct.value}")
    if a.max_drawdown_marked:
        print(
            f"Max DD (marked):   {a.max_drawdown_marked.max_drawdown_pct.value}% "
            f"obs={a.max_drawdown_marked.observation_count}"
        )
    if a.max_drawdown_realized_balance:
        print(
            f"Max DD (balance):  {a.max_drawdown_realized_balance.max_drawdown_pct.value}% "
            f"obs={a.max_drawdown_realized_balance.observation_count}"
        )
    print(f"Equity obs:        {a.equity_observation_count}")
    print(f"Data warnings:     {list(a.data_quality_warnings) or 'none'}")
    print(f"DB: {db}")
    print("NOTE: Synthetic local simulation only — not live trading performance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
