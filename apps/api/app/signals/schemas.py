"""Pydantic schemas for signals-only API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CandleIn(BaseModel):
    start: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class EvaluateRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", max_length=32)
    category: str = Field(default="linear", pattern="^(spot|linear)$")
    interval: str = Field(default="15", max_length=8)
    now_ms: int | None = None
    data_path: str = "public_fixture"
    candles: list[CandleIn] = Field(default_factory=list)


class EvaluateResponse(BaseModel):
    decision: dict[str, Any]
    execution_allowed: bool = False
    trading_enabled: bool = False
    private_api_used: bool = False
    note: str = "Signals only — not an order and not live trading"
