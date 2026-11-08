"""Analytics DTOs — decimal-safe, availability-aware."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class MetricAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNBOUNDED = "unbounded"  # e.g. profit factor with zero losses and positive profit
    EMPTY = "empty"


class SeriesType(str, Enum):
    REALIZED_BALANCE = "realized_balance"
    MARKED_EQUITY = "marked_equity"


@dataclass(frozen=True)
class ClosedTradeMetrics:
    position_id: str
    session_id: str
    symbol: str
    category: str
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    entry_fee: Decimal
    exit_fee: Decimal
    gross_realized_pnl: Decimal
    net_realized_pnl: Decimal  # authoritative from position.realized_pnl (net of fees)
    exit_reason: str | None
    opened_ms: int
    closed_ms: int
    holding_duration_ms: int
    data_label: str = "SIMULATED / PAPER ONLY"


@dataclass(frozen=True)
class OptionalDecimal:
    value: Decimal | None
    status: MetricAvailability
    reason: str | None = None


@dataclass(frozen=True)
class EquityPoint:
    as_of_ms: int
    value: Decimal
    valuation_status: str
    series_type: SeriesType


@dataclass(frozen=True)
class DrawdownResult:
    max_drawdown_pct: OptionalDecimal
    max_drawdown_amount: OptionalDecimal
    peak_ms: int | None
    trough_ms: int | None
    series_type: SeriesType
    observation_count: int
    sparse_warning: bool
    label: str
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SymbolBreakdown:
    symbol: str
    closed_trades: int
    winners: int
    losers: int
    breakeven: int
    net_realized_pnl: Decimal
    fees: Decimal
    win_rate_pct: OptionalDecimal


@dataclass(frozen=True)
class SessionAnalytics:
    session_id: str
    currency: str
    initial_balance: Decimal
    closed_trades: int
    open_positions: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate_pct: OptionalDecimal
    gross_profit: Decimal
    gross_loss: Decimal
    net_realized_pnl: Decimal
    total_fees: Decimal
    profit_factor: OptionalDecimal
    average_win: OptionalDecimal
    average_loss: OptionalDecimal
    expectancy: OptionalDecimal
    average_trade_pnl: OptionalDecimal
    best_trade_pnl: OptionalDecimal
    worst_trade_pnl: OptionalDecimal
    average_holding_ms: OptionalDecimal
    realized_return_pct: OptionalDecimal  # net / initial_balance × 100
    fee_drag: Decimal
    equity_observation_count: int
    marked_equity_observation_count: int
    realized_balance_observation_count: int
    max_drawdown_marked: DrawdownResult | None
    max_drawdown_realized_balance: DrawdownResult | None
    symbol_breakdown: tuple[SymbolBreakdown, ...]
    data_quality_warnings: tuple[str, ...]
    data_label: str = "SIMULATED / PAPER ONLY"
    simulated: bool = True
    extras: dict[str, Any] = field(default_factory=dict)
