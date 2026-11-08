"""Reuse 67A analytics definitions over the isolated backtest journal."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.backtest.models import optional_metric_dict, qstr
from agent.backtest.store import open_isolated_read_store
from agent.paper.analytics.equity_curve import (
    marked_equity_series,
    realized_balance_series,
)
from agent.paper.analytics.models import SessionAnalytics
from agent.paper.analytics.service import (
    AnalyticsError,
    compute_session_analytics,
    list_trade_metrics,
)
from agent.paper.equity import reconcile_equity
from agent.paper.models import PositionStatus
from agent.paper.store import PaperStore


PERFORMANCE_LABEL = "HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE"


def _drawdown_dict(dd: Any) -> dict[str, Any] | None:
    if dd is None:
        return None
    return {
        "max_drawdown_pct": optional_metric_dict(dd.max_drawdown_pct),
        "max_drawdown_amount": optional_metric_dict(dd.max_drawdown_amount),
        "peak_ms": dd.peak_ms,
        "trough_ms": dd.trough_ms,
        "series_type": dd.series_type.value
        if hasattr(dd.series_type, "value")
        else str(dd.series_type),
        "observation_count": dd.observation_count,
        "sparse_warning": dd.sparse_warning,
        "label": dd.label,
        "notes": list(dd.notes),
    }


def session_analytics_to_dict(sa: SessionAnalytics) -> dict[str, Any]:
    return {
        "session_id": sa.session_id,
        "currency": sa.currency,
        "initial_balance": str(sa.initial_balance),
        "closed_trades": sa.closed_trades,
        "open_positions": sa.open_positions,
        "winning_trades": sa.winning_trades,
        "losing_trades": sa.losing_trades,
        "breakeven_trades": sa.breakeven_trades,
        "win_rate_pct": optional_metric_dict(sa.win_rate_pct),
        "gross_profit": str(sa.gross_profit),
        "gross_loss": str(sa.gross_loss),
        "net_realized_pnl": str(sa.net_realized_pnl),
        "total_fees": str(sa.total_fees),
        "profit_factor": optional_metric_dict(sa.profit_factor),
        "average_win": optional_metric_dict(sa.average_win),
        "average_loss": optional_metric_dict(sa.average_loss),
        "expectancy": optional_metric_dict(sa.expectancy),
        "average_trade_pnl": optional_metric_dict(sa.average_trade_pnl),
        "best_trade_pnl": optional_metric_dict(sa.best_trade_pnl),
        "worst_trade_pnl": optional_metric_dict(sa.worst_trade_pnl),
        "average_holding_ms": optional_metric_dict(sa.average_holding_ms),
        "realized_return_pct": optional_metric_dict(sa.realized_return_pct),
        "fee_drag": str(sa.fee_drag),
        "equity_observation_count": sa.equity_observation_count,
        "marked_equity_observation_count": sa.marked_equity_observation_count,
        "realized_balance_observation_count": sa.realized_balance_observation_count,
        "max_drawdown_marked": _drawdown_dict(sa.max_drawdown_marked),
        "max_drawdown_realized_balance": _drawdown_dict(sa.max_drawdown_realized_balance),
        "symbol_breakdown": [
            {
                "symbol": s.symbol,
                "closed_trades": s.closed_trades,
                "winners": s.winners,
                "losers": s.losers,
                "breakeven": s.breakeven,
                "net_realized_pnl": str(s.net_realized_pnl),
                "fees": str(s.fees),
                "win_rate_pct": optional_metric_dict(s.win_rate_pct),
            }
            for s in sa.symbol_breakdown
        ],
        "data_quality_warnings": list(sa.data_quality_warnings),
        "data_label": PERFORMANCE_LABEL,
        "simulated": True,
        "metric_semantics": "67A paper analytics definitions (realized net of fees)",
    }


def collect_analytics(
    *,
    journal_path: str | Path,
    session_id: str,
) -> dict[str, Any]:
    read = open_isolated_read_store(journal_path)
    try:
        sa = compute_session_analytics(read, session_id)
    except AnalyticsError as exc:
        return {
            "error": {"code": exc.code, "message": exc.message},
            "data_label": PERFORMANCE_LABEL,
        }
    payload = session_analytics_to_dict(sa)
    trades, warnings = list_trade_metrics(read, session_id, limit=500, offset=0)
    payload["trades"] = [
        {
            "position_id": t.position_id,
            "symbol": t.symbol,
            "category": t.category,
            "quantity": str(t.quantity),
            "entry_price": str(t.entry_price),
            "exit_price": str(t.exit_price),
            "entry_fee": str(t.entry_fee),
            "exit_fee": str(t.exit_fee),
            "gross_realized_pnl": str(t.gross_realized_pnl),
            "net_realized_pnl": str(t.net_realized_pnl),
            "exit_reason": t.exit_reason,
            "opened_ms": t.opened_ms,
            "closed_ms": t.closed_ms,
            "holding_duration_ms": t.holding_duration_ms,
        }
        for t in trades
    ]
    if warnings:
        payload["data_quality_warnings"] = list(
            dict.fromkeys([*payload["data_quality_warnings"], *warnings])
        )

    snaps = read.list_equity_snapshots(session_id, limit=5000)
    opens = read.list_positions(session_id, status=PositionStatus.OPEN.value, limit=50)
    marked, marked_warn = marked_equity_series(snaps)
    realized, realized_warn = realized_balance_series(snaps)
    if marked_warn or realized_warn:
        payload["data_quality_warnings"] = list(
            dict.fromkeys(
                [*payload["data_quality_warnings"], *marked_warn, *realized_warn]
            )
        )
    payload["equity_curve"] = {
        "marked_equity": [
            {
                "as_of_ms": p.as_of_ms,
                "value": str(p.value),
                "valuation_status": p.valuation_status,
            }
            for p in marked
        ],
        "realized_balance": [
            {
                "as_of_ms": p.as_of_ms,
                "value": str(p.value),
                "valuation_status": p.valuation_status,
            }
            for p in realized
        ],
        "note": (
            "Marked equity and realized balance are separate series; "
            "observed drawdown is snapshot-based, not true intraperiod max."
        ),
    }
    payload["open_position_summaries"] = [
        {
            "position_id": p.position_id,
            "symbol": p.symbol,
            "quantity": str(p.quantity),
            "entry_price": str(p.entry_price),
            "mark_price": None if p.mark_price is None else str(p.mark_price),
            "unrealized_note": "Open at dataset end — not force-closed",
        }
        for p in opens
    ]
    return payload


def final_account_snapshot(store: PaperStore, session_id: str) -> dict[str, str | None]:
    sess = store.get_session(session_id)
    if sess is None:
        return {
            "available_balance": None,
            "reserved_capital": None,
            "marked_equity": None,
        }
    opens = store.get_open_positions(session_id)
    eq = reconcile_equity(session=sess, open_positions=opens)
    marked = qstr(eq.marked_equity) if eq.equity_available else None
    return {
        "available_balance": qstr(sess.available_balance),
        "reserved_capital": qstr(sess.reserved_capital),
        "marked_equity": marked,
    }
