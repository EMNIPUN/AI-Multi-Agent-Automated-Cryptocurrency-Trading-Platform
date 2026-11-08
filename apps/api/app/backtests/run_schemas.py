"""Request/response models for controlled backtest run API (Prompt 68C)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class BacktestRunDisabledResponse(BaseModel):
    detail: str = "backtest_run_api_disabled"
    message: str = (
        "Backtest run API is disabled. Set BACKTEST_RUN_API_ENABLED=true for local use."
    )


class BacktestRunRequest(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=32)
    market_type: Literal["spot", "linear"] = "spot"
    interval: str = Field(..., min_length=1, max_length=8)
    start_ms: int = Field(..., gt=0)
    end_ms: int = Field(..., gt=0)
    initial_capital: str = Field(default="1000", max_length=32)
    fee_rate: str = Field(default="0.001", max_length=32)
    slippage_bps: str = Field(default="5", max_length=32)
    risk_mode: Literal["signal_only", "portfolio"] = "signal_only"
    data_source: Literal["bybit_public", "offline_fixture"] = "bybit_public"
    # Content-addressed cache key only — never a filesystem path.
    dataset_hash: str | None = Field(default=None, max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=128)
    grace_ms: int = Field(default=2000, ge=0, le=60_000)

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("interval")
    @classmethod
    def _strip_interval(cls, v: str) -> str:
        return v.strip()

    @field_validator("idempotency_key")
    @classmethod
    def _strip_key(cls, v: str | None) -> str | None:
        if v is None:
            return None
        text = v.strip()
        return text or None

    @field_validator("dataset_hash")
    @classmethod
    def _hash_or_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        text = v.strip().lower()
        if not text:
            return None
        if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
            raise ValueError("dataset_hash must be 64 lowercase hex chars")
        return text


class BacktestRunAcceptedResponse(BaseModel):
    job_id: str
    status: str
    message: str = "Backtest accepted — HISTORICAL SIMULATION only"
    performance_label: str = (
        "HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE"
    )
    estimated_candles: int | None = None
    idempotent_replay: bool = False


class BacktestJobStatusResponse(BaseModel):
    job_id: str
    status: str
    run_id: str | None = None
    created_ms: int
    started_ms: int | None = None
    finished_ms: int | None = None
    phase: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    request_summary: dict[str, Any] = Field(default_factory=dict)
    dataset_hash: str | None = None
    result_hash: str | None = None
    performance_label: str = (
        "HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE"
    )
    linear_limitation: str | None = None


class BacktestRunCapabilitiesResponse(BaseModel):
    run_api_enabled: bool
    read_api_enabled: bool
    symbols: list[str]
    market_types: list[str]
    intervals: list[str]
    risk_modes: list[str]
    data_sources: list[str]
    max_candles_per_run: int
    max_range_ms: int
    max_simultaneous_runs: int
    max_queued_runs: int
    max_runtime_seconds: int
    performance_label: str = (
        "HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE"
    )
    linear_note: str = (
        "Linear historical candles still use spot-like long-only simulation — "
        "not a leveraged Futures backtest."
    )
    note: str = (
        "POST /api/v1/backtests/runs starts one isolated historical simulation. "
        "GET never starts execution."
    )
