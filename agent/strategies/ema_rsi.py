from agent.config import AgentSettings
from agent.market_data import Candle, ema, rsi
from agent.strategies.base import Signal, SignalAction


class EmaRsiStrategy:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings

    def evaluate(self, candles: list[Candle]) -> Signal:
        closes = [c.close for c in candles]
        if len(closes) < self.settings.ema_slow + 2:
            return Signal(
                action=SignalAction.HOLD,
                reason="Not enough candles",
                price=closes[-1] if closes else 0.0,
            )

        fast = ema(closes, self.settings.ema_fast)
        slow = ema(closes, self.settings.ema_slow)
        rsi_vals = rsi(closes, self.settings.rsi_period)

        i = len(closes) - 1
        prev = i - 1
        if (
            fast[i] is None
            or slow[i] is None
            or fast[prev] is None
            or slow[prev] is None
            or rsi_vals[i] is None
        ):
            return Signal(
                action=SignalAction.HOLD,
                reason="Indicators warming up",
                price=closes[i],
            )

        f0, f1 = fast[prev], fast[i]
        s0, s1 = slow[prev], slow[i]
        r = rsi_vals[i]
        price = closes[i]

        cross_up = f0 <= s0 and f1 > s1
        cross_down = f0 >= s0 and f1 < s1

        if cross_up and r < self.settings.rsi_overbought:
            return Signal(
                action=SignalAction.BUY,
                reason=(
                    f"EMA{self.settings.ema_fast} crossed above "
                    f"EMA{self.settings.ema_slow}, RSI={r:.1f}"
                ),
                price=price,
                ema_fast=f1,
                ema_slow=s1,
                rsi=r,
            )

        if cross_down and r > self.settings.rsi_oversold:
            return Signal(
                action=SignalAction.SELL,
                reason=(
                    f"EMA{self.settings.ema_fast} crossed below "
                    f"EMA{self.settings.ema_slow}, RSI={r:.1f}"
                ),
                price=price,
                ema_fast=f1,
                ema_slow=s1,
                rsi=r,
            )

        return Signal(
            action=SignalAction.HOLD,
            reason=f"No cross (EMA {f1:.6g}/{s1:.6g}, RSI={r:.1f})",
            price=price,
            ema_fast=f1,
            ema_slow=s1,
            rsi=r,
        )
