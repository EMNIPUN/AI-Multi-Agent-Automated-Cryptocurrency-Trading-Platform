"""Thin adapter over the existing Multi-Agent SignalPipeline (persist=False)."""

from __future__ import annotations

from agent.candle_time import candle_close_ms
from agent.market_data import Candle
from agent.multi_agent.config import SignalPipelineConfig
from agent.multi_agent.pipeline import SignalPipeline
from agent.multi_agent.risk_agent import SignalRiskState
from agent.multi_agent.types import CoordinatorDecision


def make_pipeline(
    config: SignalPipelineConfig,
    *,
    risk_state: SignalRiskState | None = None,
) -> SignalPipeline:
    return SignalPipeline(
        config=config,
        risk_state=risk_state or SignalRiskState(),
        persist=False,
        history_store=None,
        require_persist=False,
    )


def replay_now_ms(*, candle_start_ms: int, interval: str, grace_ms: int) -> int:
    """Clock after candle N is confirmed — agents must not see N+1."""
    return candle_close_ms(candle_start_ms, interval) + max(0, grace_ms)


def evaluate_at_index(
    pipeline: SignalPipeline,
    *,
    candles: list[Candle],
    index: int,
    symbol: str,
    category: str,
    interval: str,
    grace_ms: int,
) -> tuple[CoordinatorDecision, int]:
    """
    Evaluate using confirmed candles [0..index] only.

    Look-ahead ban: never pass candles beyond ``index``.
    """
    if index < 0 or index >= len(candles):
        raise IndexError("candle index out of range")
    window = candles[: index + 1]
    bar = window[-1]
    now_ms = replay_now_ms(
        candle_start_ms=int(bar.start),
        interval=interval,
        grace_ms=grace_ms,
    )
    decision = pipeline.evaluate(
        symbol=symbol,
        category=category,
        interval=interval,
        candles=window,
        now_ms=now_ms,
        data_path="historical_replay",
    )
    return decision, now_ms
