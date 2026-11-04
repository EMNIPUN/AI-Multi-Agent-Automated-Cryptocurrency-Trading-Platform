"""Stable signal identity for confirmed-bar actionable signals."""

from __future__ import annotations

import hashlib

STRATEGY_EMA_RSI_ID = "ema_rsi"
STRATEGY_EMA_RSI_VERSION = "1"


def strategy_config_identity(
    *,
    ema_fast: int,
    ema_slow: int,
    rsi_period: int,
    rsi_overbought: float,
    rsi_oversold: float,
) -> str:
    raw = (
        f"ema:{ema_fast}/{ema_slow}|rsi:{rsi_period}|"
        f"ob:{rsi_overbought}|os:{rsi_oversold}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_signal_id(
    *,
    symbol: str,
    category: str,
    interval: str,
    strategy_id: str,
    strategy_version: str,
    candle_close_ms: int,
    config_id: str,
    action: str,
) -> str:
    """
    Deterministic identity for an actionable signal on a specific closed candle.

    Same inputs always yield the same id (restart-safe dedupe key).
    """
    parts = [
        symbol.upper(),
        category.lower(),
        interval,
        strategy_id,
        strategy_version,
        str(int(candle_close_ms)),
        config_id,
        action.upper(),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"sig_{digest}"


def correlation_id_from_signal(signal_id: str) -> str:
    """Map signal id into a short correlation token for Phase 1B intents."""
    # Keep alphanumeric for orderLinkId fingerprint material.
    body = signal_id.removeprefix("sig_")[:24]
    return f"s{body}"
