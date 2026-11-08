"""Pydantic response schemas for paper read API — decimal strings, paper-only labels."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PaperLabelMixin(BaseModel):
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"
    simulated: bool = True


class PaperStatusResponse(BaseModel):
    paper_read_api_enabled: bool
    broker_auto_attach: bool = False
    execution_allowed: bool = False
    trading_endpoints: bool = False
    db_configured: bool
    db_present: bool
    schema_version: int | None = None
    session_count: int | None = None
    note: str
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"


class PaperSessionSummary(PaperLabelMixin):
    session_id: str
    status: str
    currency: str
    initial_balance: str
    available_balance: str
    reserved_capital: str
    realized_pnl: str
    fees_paid: str
    created_ms: int
    updated_ms: int
    open_position_count: int | None = None


class PaperSessionListResponse(BaseModel):
    items: list[PaperSessionSummary]
    total: int
    limit: int
    offset: int
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"


class PaperAccountResponse(PaperLabelMixin):
    session_id: str
    status: str
    currency: str
    initial_balance: str
    available_balance: str
    reserved_capital: str
    realized_pnl: str
    fees_paid: str
    open_position_count: int
    unrealized_pnl: str | None
    unrealized_pnl_status: Literal["ok", "unavailable", "stale_or_partial", "none"]
    marked_equity: str | None
    marked_equity_status: Literal["ok", "unavailable", "stale_or_partial"]
    created_ms: int
    updated_ms: int
    note: str = (
        "Available cash ≠ equity. Marked equity only when persisted marks exist."
    )


class PaperPositionItem(PaperLabelMixin):
    position_id: str
    session_id: str
    symbol: str
    category: str
    side: Literal["LONG"] = "LONG"
    status: str
    quantity: str
    entry_price: str
    entry_fee: str
    stop_loss: str | None
    take_profit: str | None
    opened_ms: int
    closed_ms: int | None
    exit_price: str | None
    exit_fee: str
    exit_reason: str | None
    realized_pnl: str
    mark_price: str | None
    unrealized_pnl: str | None
    unrealized_pnl_status: Literal["ok", "unavailable"]
    entry_signal_id: str
    entry_order_id: str
    exit_order_id: str | None


class PaperPositionListResponse(BaseModel):
    items: list[PaperPositionItem]
    limit: int
    offset: int
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"
    category_note: str = "MVP supports spot-like unleveraged longs only"


class PaperOrderItem(PaperLabelMixin):
    order_id: str
    session_id: str
    source_signal_id: str
    symbol: str
    category: str
    side: str
    quantity: str
    intended_entry_price: str
    status: str
    created_ms: int
    filled_ms: int | None
    fill_price: str | None
    fee: str
    slippage: str
    rejection_reason: str | None
    stop_loss: str | None
    take_profit: str | None


class PaperOrderListResponse(BaseModel):
    items: list[PaperOrderItem]
    limit: int
    offset: int
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"


class PaperFillItem(PaperLabelMixin):
    fill_id: str
    order_id: str
    session_id: str
    symbol: str
    side: str
    quantity: str
    price: str
    fee: str
    slippage: str
    filled_ms: int
    candle_start_ms: int
    role: str


class PaperFillListResponse(BaseModel):
    items: list[PaperFillItem]
    limit: int
    offset: int
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"


class PaperEventItem(BaseModel):
    event_id: str
    session_id: str
    event_type: str
    payload_json: str
    created_ms: int
    idempotency_key: str
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"


class PaperEventListResponse(BaseModel):
    items: list[PaperEventItem]
    limit: int
    offset: int
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"


class PaperSignalLinkResponse(BaseModel):
    source_signal_id: str
    linked: bool
    orders: list[PaperOrderItem]
    message: str
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"


class PaperDisabledResponse(BaseModel):
    paper_read_api_enabled: bool = False
    detail: str = "paper_read_api_disabled"
    message: str = (
        "Paper read API is disabled. Set PAPER_READ_API_ENABLED=true for local use."
    )
    broker_auto_attach: bool = False
    trading_endpoints: bool = False


class OptionalMetric(BaseModel):
    value: str | None
    status: str
    reason: str | None = None


class DrawdownApi(BaseModel):
    max_drawdown_pct: OptionalMetric
    max_drawdown_amount: OptionalMetric
    peak_ms: int | None
    trough_ms: int | None
    series_type: str
    observation_count: int
    sparse_warning: bool
    label: str
    notes: list[str] = []


class SymbolBreakdownApi(BaseModel):
    symbol: str
    closed_trades: int
    winners: int
    losers: int
    breakeven: int
    net_realized_pnl: str
    fees: str
    win_rate_pct: OptionalMetric


class PaperAnalyticsResponse(BaseModel):
    session_id: str
    currency: str
    initial_balance: str
    closed_trades: int
    open_positions: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate_pct: OptionalMetric
    gross_profit: str
    gross_loss: str
    net_realized_pnl: str
    total_fees: str
    profit_factor: OptionalMetric
    average_win: OptionalMetric
    average_loss: OptionalMetric
    expectancy: OptionalMetric
    average_trade_pnl: OptionalMetric
    best_trade_pnl: OptionalMetric
    worst_trade_pnl: OptionalMetric
    average_holding_ms: OptionalMetric
    realized_return_pct: OptionalMetric
    fee_drag: str
    equity_observation_count: int
    marked_equity_observation_count: int
    realized_balance_observation_count: int
    max_drawdown_marked: DrawdownApi | None
    max_drawdown_realized_balance: DrawdownApi | None
    symbol_breakdown: list[SymbolBreakdownApi]
    data_quality_warnings: list[str]
    note: str = (
        "SIMULATED / PAPER ONLY — realized metrics exclude unrealized open PnL"
    )
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"
    simulated: bool = True


class PaperAnalyticsTradeItem(BaseModel):
    position_id: str
    session_id: str
    symbol: str
    category: str
    quantity: str
    entry_price: str
    exit_price: str
    entry_fee: str
    exit_fee: str
    gross_realized_pnl: str
    net_realized_pnl: str
    exit_reason: str | None
    opened_ms: int
    closed_ms: int
    holding_duration_ms: int
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"


class PaperAnalyticsTradesResponse(BaseModel):
    items: list[PaperAnalyticsTradeItem]
    limit: int
    offset: int
    warnings: list[str] = []
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"


class PaperEquityPointApi(BaseModel):
    as_of_ms: int
    value: str
    valuation_status: str
    series_type: str


class PaperAnalyticsEquityResponse(BaseModel):
    series_type: str
    points: list[PaperEquityPointApi]
    warnings: list[str] = []
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"


class PaperAnalyticsSymbolsResponse(BaseModel):
    items: list[SymbolBreakdownApi]
    data_label: Literal["SIMULATED / PAPER ONLY"] = "SIMULATED / PAPER ONLY"
