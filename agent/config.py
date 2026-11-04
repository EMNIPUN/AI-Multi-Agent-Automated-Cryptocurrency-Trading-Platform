import os
from dataclasses import dataclass

from dotenv import load_dotenv

from bot.config import _flag, is_live_mainnet

load_dotenv()


def _float(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default).strip())
    except ValueError:
        return float(default)


def _int(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default).strip())
    except ValueError:
        return int(default)


@dataclass(frozen=True)
class AgentSettings:
    enabled: bool
    dry_run: bool
    allow_live: bool
    category: str
    symbols: tuple[str, ...]
    interval: str
    poll_seconds: int
    risk_pct_equity: float
    max_open_positions: int
    daily_loss_pct: float
    leverage: int
    ema_fast: int
    ema_slow: int
    rsi_period: int
    rsi_overbought: float
    rsi_oversold: float
    take_profit_pct: float
    stop_loss_pct: float
    candle_limit: int
    candle_finalize_grace_ms: int
    max_clock_skew_ms: int
    max_candle_staleness_ms: int  # 0 = derive from interval


def load_settings() -> AgentSettings:
    symbols_raw = os.getenv("AGENT_SYMBOLS", "HYPEUSDT").strip()
    symbols = tuple(
        s.strip().upper() for s in symbols_raw.split(",") if s.strip()
    ) or ("HYPEUSDT",)

    category = os.getenv("AGENT_CATEGORY", "linear").strip().lower()
    if category not in {"linear", "spot"}:
        category = "linear"

    return AgentSettings(
        enabled=_flag("AGENT_ENABLED", "true"),
        dry_run=_flag("AGENT_DRY_RUN", "true"),
        allow_live=_flag("AGENT_ALLOW_LIVE", "false"),
        category=category,
        symbols=symbols,
        interval=os.getenv("AGENT_INTERVAL", "15").strip() or "15",
        poll_seconds=max(15, _int("AGENT_POLL_SECONDS", "60")),
        risk_pct_equity=max(0.1, min(5.0, _float("AGENT_RISK_PCT", "1.0"))),
        max_open_positions=max(1, _int("AGENT_MAX_POSITIONS", "1")),
        daily_loss_pct=max(0.5, min(20.0, _float("AGENT_DAILY_LOSS_PCT", "3.0"))),
        leverage=max(1, min(20, _int("AGENT_LEVERAGE", "3"))),
        ema_fast=max(2, _int("AGENT_EMA_FAST", "9")),
        ema_slow=max(3, _int("AGENT_EMA_SLOW", "21")),
        rsi_period=max(2, _int("AGENT_RSI_PERIOD", "14")),
        rsi_overbought=_float("AGENT_RSI_OVERBOUGHT", "70"),
        rsi_oversold=_float("AGENT_RSI_OVERSOLD", "30"),
        take_profit_pct=max(0.1, _float("AGENT_TP_PCT", "1.5")),
        stop_loss_pct=max(0.1, _float("AGENT_SL_PCT", "1.0")),
        candle_limit=max(50, _int("AGENT_CANDLE_LIMIT", "120")),
        candle_finalize_grace_ms=max(0, _int("AGENT_CANDLE_GRACE_MS", "2000")),
        max_clock_skew_ms=max(0, _int("AGENT_MAX_CLOCK_SKEW_MS", "5000")),
        max_candle_staleness_ms=max(0, _int("AGENT_MAX_CANDLE_STALENESS_MS", "0")),
    )


def live_orders_blocked(settings: AgentSettings) -> str | None:
    """Return a reason string if real orders must not be sent."""
    if settings.dry_run:
        return None
    if is_live_mainnet() and not settings.allow_live:
        return (
            "Mainnet live orders blocked. Set AGENT_ALLOW_LIVE=true "
            "only after Testnet proof, or keep AGENT_DRY_RUN=true / use Testnet."
        )
    return None
