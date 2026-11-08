from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


ConditionResult = Literal["PASS", "FAIL", "NOT_EVALUATED", "UNKNOWN"]


@dataclass(frozen=True)
class Signal:
    action: SignalAction
    reason: str
    price: float
    ema_fast: float | None = None
    ema_slow: float | None = None
    rsi: float | None = None
    # Confirmed-bar metadata (Phase 1D); 0 / "" when not applicable.
    candle_start_ms: int = 0
    candle_close_ms: int = 0
    signal_id: str = ""
    explanation_code: str = ""
    strategy_id: str = ""
    strategy_version: str = ""
    conditions: tuple[tuple[str, ConditionResult], ...] = field(default_factory=tuple)
