from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from pybit.unified_trading import HTTP

from agent.config import AgentSettings, live_orders_blocked
from agent.strategies.base import Signal, SignalAction
from bot.market import get_instrument, normalize_qty, split_symbol
from bot.utils import format_decimal


@dataclass
class RiskState:
    day: date = field(default_factory=date.today)
    start_equity: float | None = None
    peak_equity: float | None = None
    halted: bool = False
    halt_reason: str = ""


@dataclass(frozen=True)
class TradePlan:
    symbol: str
    side: str  # Buy / Sell
    qty: str
    reduce_only: bool
    take_profit: str | None = None
    stop_loss: str | None = None
    reason: str = ""


class RiskManager:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self.state = RiskState()

    def update_equity(self, equity: float | None) -> None:
        if equity is None:
            return
        today = date.today()
        if self.state.day != today or self.state.start_equity is None:
            self.state = RiskState(day=today, start_equity=equity, peak_equity=equity)
            return
        self.state.peak_equity = max(self.state.peak_equity or equity, equity)
        start = self.state.start_equity or equity
        if start > 0:
            drawdown_pct = ((start - equity) / start) * 100
            if drawdown_pct >= self.settings.daily_loss_pct:
                self.state.halted = True
                self.state.halt_reason = (
                    f"Daily loss limit hit ({drawdown_pct:.2f}% >= "
                    f"{self.settings.daily_loss_pct}%)"
                )

    def open_position_count(self, positions: dict[str, dict | None]) -> int:
        return sum(1 for pos in positions.values() if pos)

    def plan_trade(
        self,
        session: HTTP,
        symbol: str,
        signal: Signal,
        position: dict | None,
        equity: float | None,
        open_count: int,
    ) -> TradePlan | None:
        block = live_orders_blocked(self.settings)
        # dry_run still produces plans; block only matters at execute time
        if self.state.halted:
            return None
        if signal.action == SignalAction.HOLD:
            return None

        category = self.settings.category
        price = Decimal(str(signal.price))

        # Close / reverse logic
        if position:
            pos_side = position.get("side")
            if signal.action == SignalAction.SELL and pos_side == "Buy":
                qty = normalize_qty(
                    session,
                    category,
                    symbol,
                    Decimal(str(position["size"])),
                )
                if not qty:
                    return None
                return TradePlan(
                    symbol=symbol,
                    side="Sell",
                    qty=qty,
                    reduce_only=(category == "linear"),
                    reason=f"Close long: {signal.reason}",
                )
            if signal.action == SignalAction.BUY and pos_side == "Sell":
                qty = normalize_qty(
                    session,
                    category,
                    symbol,
                    Decimal(str(position["size"])),
                )
                if not qty:
                    return None
                return TradePlan(
                    symbol=symbol,
                    side="Buy",
                    qty=qty,
                    reduce_only=(category == "linear"),
                    reason=f"Close short: {signal.reason}",
                )
            # Same-direction signal while in position → hold
            return None

        # Flat: only open if under max positions
        if open_count >= self.settings.max_open_positions:
            return None

        if category == "spot" and signal.action == SignalAction.SELL:
            # Spot agent does not naked-short
            return None

        if equity is None or equity <= 0 or price <= 0:
            return None

        side = "Buy" if signal.action == SignalAction.BUY else "Sell"
        notional = Decimal(str(equity)) * (
            Decimal(str(self.settings.risk_pct_equity)) / Decimal("100")
        )
        if category == "linear":
            # Risk % is treated as margin budget; size = margin * leverage
            notional = notional * Decimal(self.settings.leverage)

        raw_qty = notional / price
        qty = normalize_qty(session, category, symbol, raw_qty)
        if not qty:
            instrument = get_instrument(session, category, symbol)
            min_qty = (instrument or {}).get("lotSizeFilter", {}).get("minOrderQty")
            print(
                f"[{symbol}] size below exchange minimum "
                f"(wanted ~{format_decimal(raw_qty)}, min={min_qty}). Skip."
            )
            return None

        # Affordability check vs min notional
        instrument = get_instrument(session, category, symbol)
        if instrument:
            min_qty = Decimal(
                (instrument.get("lotSizeFilter") or {}).get("minOrderQty") or "0"
            )
            min_cost = min_qty * price
            if category == "linear":
                min_margin = min_cost / Decimal(self.settings.leverage)
                if Decimal(str(equity)) < min_margin:
                    print(
                        f"[{symbol}] equity too small for min contract "
                        f"(need margin ≈ {format_decimal(min_margin)}). Skip."
                    )
                    return None
            else:
                _, quote = split_symbol(symbol)
                if Decimal(str(equity)) < min_cost:
                    print(
                        f"[{symbol}] equity too small for min spot qty "
                        f"(need ≈ {format_decimal(min_cost)} {quote}). Skip."
                    )
                    return None

        tp = sl = None
        if category == "linear":
            if side == "Buy":
                tp_px = price * (
                    Decimal("1")
                    + Decimal(str(self.settings.take_profit_pct)) / Decimal("100")
                )
                sl_px = price * (
                    Decimal("1")
                    - Decimal(str(self.settings.stop_loss_pct)) / Decimal("100")
                )
            else:
                tp_px = price * (
                    Decimal("1")
                    - Decimal(str(self.settings.take_profit_pct)) / Decimal("100")
                )
                sl_px = price * (
                    Decimal("1")
                    + Decimal(str(self.settings.stop_loss_pct)) / Decimal("100")
                )
            tick = Decimal(
                ((instrument or {}).get("priceFilter") or {}).get("tickSize") or "0.01"
            )
            from bot.utils import floor_to_step

            tp = format_decimal(floor_to_step(tp_px, tick))
            sl = format_decimal(floor_to_step(sl_px, tick))

        _ = block  # documented at execute time
        return TradePlan(
            symbol=symbol,
            side=side,
            qty=qty,
            reduce_only=False,
            take_profit=tp,
            stop_loss=sl,
            reason=signal.reason,
        )
