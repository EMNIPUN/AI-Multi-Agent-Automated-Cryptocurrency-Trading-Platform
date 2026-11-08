"""Paper broker domain models — explicitly simulated, never exchange orders."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExitReason(str, Enum):
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    SIGNAL_SELL = "SIGNAL_SELL"
    MANUAL = "MANUAL"


class SessionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class PaperCandle:
    """Confirmed OHLC bar for simulation (oldest→newest processing)."""

    start_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")
    symbol: str = ""
    interval: str = ""

    def valid(self) -> bool:
        try:
            if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
                return False
            if self.high < self.low:
                return False
            if self.high < max(self.open, self.close):
                return False
            if self.low > min(self.open, self.close):
                return False
            return True
        except Exception:  # noqa: BLE001
            return False


@dataclass
class PaperSession:
    session_id: str
    initial_balance: Decimal
    available_balance: Decimal
    reserved_capital: Decimal
    realized_pnl: Decimal
    fees_paid: Decimal
    status: SessionStatus
    created_ms: int
    updated_ms: int
    config_json: str
    currency: str = "USDT"


@dataclass
class PaperOrder:
    order_id: str
    session_id: str
    source_signal_id: str
    symbol: str
    category: str
    side: OrderSide
    quantity: Decimal
    intended_entry_price: Decimal
    status: OrderStatus
    created_ms: int
    filled_ms: int | None = None
    fill_price: Decimal | None = None
    fee: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    rejection_reason: str | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    signal_candle_start_ms: int | None = None
    simulated: bool = True


@dataclass
class PaperFill:
    fill_id: str
    order_id: str
    session_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    fee: Decimal
    slippage: Decimal
    filled_ms: int
    candle_start_ms: int
    role: str  # entry | exit


@dataclass
class PaperPosition:
    position_id: str
    session_id: str
    symbol: str
    category: str
    status: PositionStatus
    quantity: Decimal
    entry_price: Decimal
    entry_fee: Decimal
    entry_order_id: str
    entry_signal_id: str
    stop_loss: Decimal | None
    take_profit: Decimal | None
    opened_ms: int
    closed_ms: int | None = None
    exit_price: Decimal | None = None
    exit_fee: Decimal = Decimal("0")
    exit_order_id: str | None = None
    exit_reason: str | None = None
    realized_pnl: Decimal = Decimal("0")
    mark_price: Decimal | None = None
    unrealized_pnl: Decimal = Decimal("0")
