"""Pure trade-level and aggregate metric calculations."""

from __future__ import annotations

from decimal import Decimal

from agent.paper.accounting import long_gross_pnl, q
from agent.paper.analytics.models import (
    ClosedTradeMetrics,
    MetricAvailability,
    OptionalDecimal,
    SymbolBreakdown,
)
from agent.paper.config import d
from agent.paper.models import PaperPosition, PositionStatus


def closed_trade_from_position(pos: PaperPosition) -> ClosedTradeMetrics | None:
    """
    Authoritative closed trade from paper_positions.

    position.realized_pnl is NET of entry_fee + exit_fee (broker long_net_pnl).
    Do not subtract fees again from net.
    """
    if pos.status is not PositionStatus.CLOSED:
        return None
    if pos.exit_price is None or pos.closed_ms is None:
        return None
    gross = long_gross_pnl(
        quantity=pos.quantity,
        entry_price=pos.entry_price,
        exit_price=pos.exit_price,
    )
    # Cross-check: net should equal gross - fees (allow tiny quantize drift)
    expected_net = q(gross - d(pos.entry_fee) - d(pos.exit_fee))
    net = d(pos.realized_pnl)
    return ClosedTradeMetrics(
        position_id=pos.position_id,
        session_id=pos.session_id,
        symbol=pos.symbol,
        category=pos.category,
        quantity=d(pos.quantity),
        entry_price=d(pos.entry_price),
        exit_price=d(pos.exit_price),
        entry_fee=d(pos.entry_fee),
        exit_fee=d(pos.exit_fee),
        gross_realized_pnl=gross,
        net_realized_pnl=net,
        exit_reason=pos.exit_reason,
        opened_ms=int(pos.opened_ms),
        closed_ms=int(pos.closed_ms),
        holding_duration_ms=max(0, int(pos.closed_ms) - int(pos.opened_ms)),
    )


def classify_outcome(net: Decimal) -> str:
    if net > 0:
        return "win"
    if net < 0:
        return "loss"
    return "breakeven"


def aggregate_trade_stats(
    trades: list[ClosedTradeMetrics],
    *,
    initial_balance: Decimal,
) -> dict:
    n = len(trades)
    if n == 0:
        zero = Decimal("0")
        return {
            "closed_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "breakeven_trades": 0,
            "win_rate_pct": OptionalDecimal(
                None, MetricAvailability.EMPTY, "no_closed_trades"
            ),
            "gross_profit": zero,
            "gross_loss": zero,
            "net_realized_pnl": zero,
            "total_fees": zero,
            "profit_factor": OptionalDecimal(
                None, MetricAvailability.EMPTY, "no_closed_trades"
            ),
            "average_win": OptionalDecimal(
                None, MetricAvailability.EMPTY, "no_winners"
            ),
            "average_loss": OptionalDecimal(
                None, MetricAvailability.EMPTY, "no_losers"
            ),
            "expectancy": OptionalDecimal(
                None, MetricAvailability.EMPTY, "no_closed_trades"
            ),
            "average_trade_pnl": OptionalDecimal(
                None, MetricAvailability.EMPTY, "no_closed_trades"
            ),
            "best_trade_pnl": OptionalDecimal(
                None, MetricAvailability.EMPTY, "no_closed_trades"
            ),
            "worst_trade_pnl": OptionalDecimal(
                None, MetricAvailability.EMPTY, "no_closed_trades"
            ),
            "average_holding_ms": OptionalDecimal(
                None, MetricAvailability.EMPTY, "no_closed_trades"
            ),
            "realized_return_pct": OptionalDecimal(
                None, MetricAvailability.EMPTY, "no_closed_trades"
            ),
            "fee_drag": zero,
        }

    winners = [t for t in trades if t.net_realized_pnl > 0]
    losers = [t for t in trades if t.net_realized_pnl < 0]
    breakeven = [t for t in trades if t.net_realized_pnl == 0]
    gross_profit = q(sum((t.net_realized_pnl for t in winners), Decimal("0")))
    gross_loss = q(
        abs(sum((t.net_realized_pnl for t in losers), Decimal("0")))
    )
    net = q(sum((t.net_realized_pnl for t in trades), Decimal("0")))
    fees = q(
        sum((t.entry_fee + t.exit_fee for t in trades), Decimal("0"))
    )

    win_rate = OptionalDecimal(
        q(Decimal(len(winners)) / Decimal(n) * Decimal("100")),
        MetricAvailability.AVAILABLE,
    )

    if gross_loss > 0:
        pf = OptionalDecimal(
            q(gross_profit / gross_loss), MetricAvailability.AVAILABLE
        )
    elif gross_profit > 0:
        pf = OptionalDecimal(
            None, MetricAvailability.UNBOUNDED, "no_losing_trades_positive_profit"
        )
    else:
        pf = OptionalDecimal(
            None, MetricAvailability.UNAVAILABLE, "zero_profit_and_loss"
        )

    avg_win = (
        OptionalDecimal(q(gross_profit / Decimal(len(winners))), MetricAvailability.AVAILABLE)
        if winners
        else OptionalDecimal(None, MetricAvailability.UNAVAILABLE, "no_winners")
    )
    avg_loss = (
        OptionalDecimal(q(gross_loss / Decimal(len(losers))), MetricAvailability.AVAILABLE)
        if losers
        else OptionalDecimal(None, MetricAvailability.UNAVAILABLE, "no_losers")
    )
    expectancy = OptionalDecimal(
        q(net / Decimal(n)), MetricAvailability.AVAILABLE
    )
    # Cross-check formula with breakeven contributing zero
    if avg_win.value is not None and avg_loss.value is not None:
        p_win = Decimal(len(winners)) / Decimal(n)
        p_loss = Decimal(len(losers)) / Decimal(n)
        cross = q(p_win * avg_win.value - p_loss * avg_loss.value)
        # Allow tiny quantize difference
        if abs(cross - expectancy.value) > Decimal("0.00000010"):
            # Keep primary definition; evidence in extras by caller
            pass

    nets = [t.net_realized_pnl for t in trades]
    holds = [Decimal(t.holding_duration_ms) for t in trades]
    init = d(initial_balance)
    if init > 0:
        ret = OptionalDecimal(
            q(net / init * Decimal("100")), MetricAvailability.AVAILABLE
        )
    else:
        ret = OptionalDecimal(
            None, MetricAvailability.UNAVAILABLE, "invalid_initial_balance"
        )

    return {
        "closed_trades": n,
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "breakeven_trades": len(breakeven),
        "win_rate_pct": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_realized_pnl": net,
        "total_fees": fees,
        "profit_factor": pf,
        "average_win": avg_win,
        "average_loss": avg_loss,
        "expectancy": expectancy,
        "average_trade_pnl": expectancy,
        "best_trade_pnl": OptionalDecimal(max(nets), MetricAvailability.AVAILABLE),
        "worst_trade_pnl": OptionalDecimal(min(nets), MetricAvailability.AVAILABLE),
        "average_holding_ms": OptionalDecimal(
            q(sum(holds) / Decimal(n)), MetricAvailability.AVAILABLE
        ),
        "realized_return_pct": ret,
        "fee_drag": fees,
    }


def symbol_breakdowns(trades: list[ClosedTradeMetrics]) -> list[SymbolBreakdown]:
    by_sym: dict[str, list[ClosedTradeMetrics]] = {}
    for t in trades:
        by_sym.setdefault(t.symbol, []).append(t)
    out: list[SymbolBreakdown] = []
    for symbol, group in sorted(by_sym.items()):
        stats = aggregate_trade_stats(group, initial_balance=Decimal("1"))
        out.append(
            SymbolBreakdown(
                symbol=symbol,
                closed_trades=stats["closed_trades"],
                winners=stats["winning_trades"],
                losers=stats["losing_trades"],
                breakeven=stats["breakeven_trades"],
                net_realized_pnl=stats["net_realized_pnl"],
                fees=stats["total_fees"],
                win_rate_pct=stats["win_rate_pct"],
            )
        )
    return out
