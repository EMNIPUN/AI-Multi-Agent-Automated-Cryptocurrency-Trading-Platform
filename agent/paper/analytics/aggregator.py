"""Assemble session analytics from closed trades + equity snapshots."""

from __future__ import annotations

from decimal import Decimal

from agent.paper.analytics.drawdown import max_drawdown
from agent.paper.analytics.equity_curve import (
    marked_equity_series,
    realized_balance_series,
    reconstruct_realized_balance_from_trades,
)
from agent.paper.analytics.metrics import (
    aggregate_trade_stats,
    closed_trade_from_position,
    symbol_breakdowns,
)
from agent.paper.analytics.models import ClosedTradeMetrics, SessionAnalytics
from agent.paper.config import d
from agent.paper.models import PaperPosition, PaperSession, PositionStatus


def build_closed_trades(
    positions: list[PaperPosition],
) -> tuple[list[ClosedTradeMetrics], list[str]]:
    trades: list[ClosedTradeMetrics] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for pos in positions:
        if pos.status is not PositionStatus.CLOSED:
            continue
        if pos.position_id in seen:
            warnings.append(f"duplicate_position_id:{pos.position_id}")
            continue
        seen.add(pos.position_id)
        trade = closed_trade_from_position(pos)
        if trade is None:
            warnings.append(f"incomplete_closed_position:{pos.position_id}")
            continue
        # Fee double-count guard: net should match gross - fees
        expected = trade.gross_realized_pnl - trade.entry_fee - trade.exit_fee
        if abs(expected - trade.net_realized_pnl) > Decimal("0.0001"):
            warnings.append(
                f"pnl_fee_mismatch:{pos.position_id}:"
                f"stored={trade.net_realized_pnl}:expected={expected}"
            )
        trades.append(trade)
    return trades, warnings


def aggregate_session_analytics(
    *,
    session: PaperSession,
    closed_positions: list[PaperPosition],
    open_position_count: int,
    equity_snapshots: list[dict],
) -> SessionAnalytics:
    trades, trade_warnings = build_closed_trades(closed_positions)
    stats = aggregate_trade_stats(
        trades, initial_balance=d(session.initial_balance)
    )
    warnings = list(trade_warnings)

    bal_series, bal_warn = realized_balance_series(equity_snapshots)
    warnings.extend(bal_warn)
    if not bal_series and trades:
        bal_series = reconstruct_realized_balance_from_trades(
            initial_balance=d(session.initial_balance),
            trade_nets_by_exit_ms=[
                (t.closed_ms, t.net_realized_pnl) for t in trades
            ],
        )
        warnings.append("realized_balance_reconstructed_from_closed_trades")

    mkt_series, mkt_warn = marked_equity_series(equity_snapshots)
    warnings.extend(mkt_warn)

    dd_bal = max_drawdown(bal_series) if bal_series else None
    dd_mkt = max_drawdown(mkt_series) if mkt_series else None
    if dd_bal and dd_bal.sparse_warning:
        warnings.append("sparse_realized_balance_drawdown")
    if dd_mkt and dd_mkt.sparse_warning:
        warnings.append("sparse_marked_equity_drawdown")

    return SessionAnalytics(
        session_id=session.session_id,
        currency=session.currency,
        initial_balance=d(session.initial_balance),
        closed_trades=stats["closed_trades"],
        open_positions=open_position_count,
        winning_trades=stats["winning_trades"],
        losing_trades=stats["losing_trades"],
        breakeven_trades=stats["breakeven_trades"],
        win_rate_pct=stats["win_rate_pct"],
        gross_profit=stats["gross_profit"],
        gross_loss=stats["gross_loss"],
        net_realized_pnl=stats["net_realized_pnl"],
        total_fees=stats["total_fees"],
        profit_factor=stats["profit_factor"],
        average_win=stats["average_win"],
        average_loss=stats["average_loss"],
        expectancy=stats["expectancy"],
        average_trade_pnl=stats["average_trade_pnl"],
        best_trade_pnl=stats["best_trade_pnl"],
        worst_trade_pnl=stats["worst_trade_pnl"],
        average_holding_ms=stats["average_holding_ms"],
        realized_return_pct=stats["realized_return_pct"],
        fee_drag=stats["fee_drag"],
        equity_observation_count=len(equity_snapshots),
        marked_equity_observation_count=len(mkt_series),
        realized_balance_observation_count=len(bal_series),
        max_drawdown_marked=dd_mkt,
        max_drawdown_realized_balance=dd_bal,
        symbol_breakdown=tuple(symbol_breakdowns(trades)),
        data_quality_warnings=tuple(dict.fromkeys(warnings)),
        extras={
            "note": (
                "realized_return_pct uses initial session capital and closed-trade "
                "net PnL only — excludes unrealized open PnL"
            ),
        },
    )
