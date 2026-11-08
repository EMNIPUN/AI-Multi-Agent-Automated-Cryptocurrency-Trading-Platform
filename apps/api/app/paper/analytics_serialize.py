"""Serialize analytics DTOs to JSON-safe decimal strings (no NaN/Infinity)."""

from __future__ import annotations

from decimal import Decimal

from agent.paper.analytics.models import (
    ClosedTradeMetrics,
    DrawdownResult,
    EquityPoint,
    OptionalDecimal,
    SessionAnalytics,
    SymbolBreakdown,
)
from apps.api.app.paper.schemas import (
    DrawdownApi,
    OptionalMetric,
    PaperAnalyticsResponse,
    PaperAnalyticsTradeItem,
    PaperEquityPointApi,
    SymbolBreakdownApi,
)


def _dec(value: Decimal | None) -> str | None:
    if value is None:
        return None
    # Reject non-finite
    if value.is_nan() or value.is_infinite():
        return None
    return format(value, "f")


def _opt(m: OptionalDecimal) -> OptionalMetric:
    return OptionalMetric(
        value=_dec(m.value),
        status=m.status.value,
        reason=m.reason,
    )


def _dd(d: DrawdownResult | None) -> DrawdownApi | None:
    if d is None:
        return None
    return DrawdownApi(
        max_drawdown_pct=_opt(d.max_drawdown_pct),
        max_drawdown_amount=_opt(d.max_drawdown_amount),
        peak_ms=d.peak_ms,
        trough_ms=d.trough_ms,
        series_type=d.series_type.value,
        observation_count=d.observation_count,
        sparse_warning=d.sparse_warning,
        label=d.label,
        notes=list(d.notes),
    )


def _sym(s: SymbolBreakdown) -> SymbolBreakdownApi:
    return SymbolBreakdownApi(
        symbol=s.symbol,
        closed_trades=s.closed_trades,
        winners=s.winners,
        losers=s.losers,
        breakeven=s.breakeven,
        net_realized_pnl=_dec(s.net_realized_pnl) or "0",
        fees=_dec(s.fees) or "0",
        win_rate_pct=_opt(s.win_rate_pct),
    )


def serialize_analytics(a: SessionAnalytics) -> PaperAnalyticsResponse:
    return PaperAnalyticsResponse(
        session_id=a.session_id,
        currency=a.currency,
        initial_balance=_dec(a.initial_balance) or "0",
        closed_trades=a.closed_trades,
        open_positions=a.open_positions,
        winning_trades=a.winning_trades,
        losing_trades=a.losing_trades,
        breakeven_trades=a.breakeven_trades,
        win_rate_pct=_opt(a.win_rate_pct),
        gross_profit=_dec(a.gross_profit) or "0",
        gross_loss=_dec(a.gross_loss) or "0",
        net_realized_pnl=_dec(a.net_realized_pnl) or "0",
        total_fees=_dec(a.total_fees) or "0",
        profit_factor=_opt(a.profit_factor),
        average_win=_opt(a.average_win),
        average_loss=_opt(a.average_loss),
        expectancy=_opt(a.expectancy),
        average_trade_pnl=_opt(a.average_trade_pnl),
        best_trade_pnl=_opt(a.best_trade_pnl),
        worst_trade_pnl=_opt(a.worst_trade_pnl),
        average_holding_ms=_opt(a.average_holding_ms),
        realized_return_pct=_opt(a.realized_return_pct),
        fee_drag=_dec(a.fee_drag) or "0",
        equity_observation_count=a.equity_observation_count,
        marked_equity_observation_count=a.marked_equity_observation_count,
        realized_balance_observation_count=a.realized_balance_observation_count,
        max_drawdown_marked=_dd(a.max_drawdown_marked),
        max_drawdown_realized_balance=_dd(a.max_drawdown_realized_balance),
        symbol_breakdown=[_sym(s) for s in a.symbol_breakdown],
        data_quality_warnings=list(a.data_quality_warnings),
    )


def serialize_trade(t: ClosedTradeMetrics) -> PaperAnalyticsTradeItem:
    return PaperAnalyticsTradeItem(
        position_id=t.position_id,
        session_id=t.session_id,
        symbol=t.symbol,
        category=t.category,
        quantity=_dec(t.quantity) or "0",
        entry_price=_dec(t.entry_price) or "0",
        exit_price=_dec(t.exit_price) or "0",
        entry_fee=_dec(t.entry_fee) or "0",
        exit_fee=_dec(t.exit_fee) or "0",
        gross_realized_pnl=_dec(t.gross_realized_pnl) or "0",
        net_realized_pnl=_dec(t.net_realized_pnl) or "0",
        exit_reason=t.exit_reason,
        opened_ms=t.opened_ms,
        closed_ms=t.closed_ms,
        holding_duration_ms=t.holding_duration_ms,
    )


def serialize_equity_point(p: EquityPoint) -> PaperEquityPointApi:
    return PaperEquityPointApi(
        as_of_ms=p.as_of_ms,
        value=_dec(p.value) or "0",
        valuation_status=p.valuation_status,
        series_type=p.series_type.value,
    )
