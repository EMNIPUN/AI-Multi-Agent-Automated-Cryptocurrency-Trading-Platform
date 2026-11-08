"""Pydantic response models for backtest read API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BacktestDisabledResponse(BaseModel):
    detail: str = "backtest_read_api_disabled"
    message: str = (
        "Backtest read API is disabled. Set BACKTEST_READ_API_ENABLED=true for local use."
    )


class BacktestStatusResponse(BaseModel):
    enabled: bool
    results_dir: str
    results_dir_exists: bool
    run_count: int = 0
    performance_label: str = (
        "HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE"
    )
    note: str = (
        "Read API discovers saved 68A reports. "
        "Execution requires separate BACKTEST_RUN_API_ENABLED + explicit POST."
    )
    mutations: bool = False
    runs_backtests: bool = False
    run_api_enabled: bool = False


class BacktestRunSummary(BaseModel):
    run_id: str
    status: str
    symbol: str | None = None
    market_type: str | None = None
    interval: str | None = None
    first_start_ms: int | None = None
    last_start_ms: int | None = None
    candle_count: int | None = None
    provenance: str | None = None
    source_kind: str | None = None
    dataset_label: str | None = None  # SYNTHETIC TEST DATA | HISTORICAL EXCHANGE DATA | …
    engine_version: str | None = None
    pipeline_version: str | None = None
    dataset_hash: str | None = None
    result_hash: str | None = None
    created_ms: int | None = None
    closed_trades: int | None = None
    open_positions: int | None = None
    net_realized_pnl: str | None = None
    performance_label: str | None = None


class BacktestRunListResponse(BaseModel):
    items: list[BacktestRunSummary]
    total: int
    limit: int
    offset: int


class BacktestRunDetailResponse(BaseModel):
    run_id: str
    status: str
    performance_label: str
    effective_config: dict[str, Any]
    dataset: dict[str, Any]
    dataset_label: str
    counters: dict[str, Any]
    eligible_candles: int | None = None
    warm_up_candles: int | None = None
    open_positions: int | None = None
    final_available_balance: str | None = None
    final_reserved_capital: str | None = None
    final_marked_equity: str | None = None
    data_quality_warnings: list[str] = Field(default_factory=list)
    result_hash: str | None = None
    created_ms: int | None = None
    error: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    decision_trace_note: str = (
        "68A persists contribution biases and final Coordinator/Risk fields per bar; "
        "full per-agent assessment payloads are not reconstructed."
    )
    reconciliation_note: str = (
        "BUY signals ≠ filled orders ≠ closed trades. See /orders and /decisions."
    )
    extras: dict[str, Any] = Field(default_factory=dict)


class BacktestMetricsResponse(BaseModel):
    run_id: str
    performance_label: str
    counters: dict[str, Any]
    analytics: dict[str, Any] | None = None
    final_available_balance: str | None = None
    final_reserved_capital: str | None = None
    final_marked_equity: str | None = None
    open_positions: int | None = None
    data_quality_warnings: list[str] = Field(default_factory=list)


class BacktestTradesResponse(BaseModel):
    run_id: str
    items: list[dict[str, Any]]
    open_positions: list[dict[str, Any]] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
    note: str = "Closed trades from 67A analytics embedded in the 68A report"


class BacktestEquityResponse(BaseModel):
    run_id: str
    marked_equity: list[dict[str, Any]] = Field(default_factory=list)
    realized_balance: list[dict[str, Any]] = Field(default_factory=list)
    note: str | None = None
    data_quality_warnings: list[str] = Field(default_factory=list)
    drawdown_note: str = (
        "Observed drawdown is snapshot-based and may understate true intraperiod max."
    )


class BacktestDecisionsResponse(BaseModel):
    run_id: str
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
    note: str = (
        "Per-bar final decision evidence from 68A. Individual agent narratives "
        "beyond contribution_biases are not persisted."
    )


class BacktestOrdersResponse(BaseModel):
    run_id: str
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
    rejection_breakdown: dict[str, int] = Field(default_factory=dict)
    note: str = (
        "Derived from 68A execution records (submit/fill/process). "
        "Not a live order blotter."
    )
