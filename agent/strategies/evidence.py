"""Build structured EMA/RSI evaluation evidence without changing trade decisions."""

from __future__ import annotations

from agent.config import AgentSettings
from agent.signal_ids import STRATEGY_EMA_RSI_ID, STRATEGY_EMA_RSI_VERSION
from agent.strategies.base import ConditionResult, Signal, SignalAction


def conditions_for_signal(
    settings: AgentSettings,
    *,
    action: SignalAction,
    cross_up: bool | None,
    cross_down: bool | None,
    rsi_value: float | None,
    indicators_ready: bool,
    enough_bars: bool,
) -> tuple[tuple[str, ConditionResult], ...]:
    def rsi_buy() -> ConditionResult:
        if rsi_value is None:
            return "UNKNOWN"
        return "PASS" if rsi_value < settings.rsi_overbought else "FAIL"

    def rsi_sell() -> ConditionResult:
        if rsi_value is None:
            return "UNKNOWN"
        return "PASS" if rsi_value > settings.rsi_oversold else "FAIL"

    return (
        ("enough_confirmed_bars", "PASS" if enough_bars else "FAIL"),
        ("indicators_ready", "PASS" if indicators_ready else "FAIL"),
        (
            "ema_cross_up",
            "PASS" if cross_up else ("FAIL" if cross_up is False else "NOT_EVALUATED"),
        ),
        (
            "ema_cross_down",
            "PASS" if cross_down else ("FAIL" if cross_down is False else "NOT_EVALUATED"),
        ),
        ("rsi_below_overbought", rsi_buy() if action is SignalAction.BUY or cross_up else "NOT_EVALUATED"),
        ("rsi_above_oversold", rsi_sell() if action is SignalAction.SELL or cross_down else "NOT_EVALUATED"),
    )


def explanation_code_for(action: SignalAction, *, enough_bars: bool, indicators_ready: bool) -> str:
    if not enough_bars:
        return "HOLD_INSUFFICIENT_BARS"
    if not indicators_ready:
        return "HOLD_INDICATORS_WARMING"
    if action is SignalAction.BUY:
        return "BUY_EMA_CROSS_UP_RSI_OK"
    if action is SignalAction.SELL:
        return "SELL_EMA_CROSS_DOWN_RSI_OK"
    return "HOLD_NO_CROSS"


def evidence_payload(signal: Signal, settings: AgentSettings) -> dict:
    return {
        "strategy_id": signal.strategy_id or STRATEGY_EMA_RSI_ID,
        "strategy_version": signal.strategy_version or STRATEGY_EMA_RSI_VERSION,
        "explanation_code": signal.explanation_code or "UNAVAILABLE",
        "ema_fast_period": settings.ema_fast,
        "ema_slow_period": settings.ema_slow,
        "rsi_period": settings.rsi_period,
        "rsi_overbought": settings.rsi_overbought,
        "rsi_oversold": settings.rsi_oversold,
        "ema_fast": signal.ema_fast,
        "ema_slow": signal.ema_slow,
        "rsi": signal.rsi,
        "candle_start_ms": signal.candle_start_ms or None,
        "candle_close_ms": signal.candle_close_ms or None,
        "conditions": [{"id": cid, "result": result} for cid, result in signal.conditions],
    }
