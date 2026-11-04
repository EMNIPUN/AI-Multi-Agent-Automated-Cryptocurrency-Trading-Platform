from dataclasses import dataclass
from enum import Enum


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class Signal:
    action: SignalAction
    reason: str
    price: float
    ema_fast: float | None = None
    ema_slow: float | None = None
    rsi: float | None = None
