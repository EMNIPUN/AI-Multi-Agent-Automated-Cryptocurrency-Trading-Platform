from agent.config import AgentSettings
from agent.market_data import Candle, ema, rsi
from agent.candle_time import candle_close_ms
from agent.signal_ids import (
    STRATEGY_EMA_RSI_ID,
    STRATEGY_EMA_RSI_VERSION,
    build_signal_id,
    strategy_config_identity,
)
from agent.strategies.base import Signal, SignalAction
from agent.strategies.evidence import conditions_for_signal, explanation_code_for


class EmaRsiStrategy:
    """
    EMA/RSI crossover strategy.

    Caller must pass **confirmed** candles only (oldest→newest). The last bar
    is treated as the actionable closed candle — never a forming bar.
    """

    strategy_id = STRATEGY_EMA_RSI_ID
    strategy_version = STRATEGY_EMA_RSI_VERSION

    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self.config_id = strategy_config_identity(
            ema_fast=settings.ema_fast,
            ema_slow=settings.ema_slow,
            rsi_period=settings.rsi_period,
            rsi_overbought=settings.rsi_overbought,
            rsi_oversold=settings.rsi_oversold,
        )

    def min_confirmed_bars(self) -> int:
        return max(self.settings.ema_slow + 2, self.settings.rsi_period + 2)

    def evaluate(
        self,
        candles: list[Candle],
        *,
        interval: str,
        symbol: str,
        category: str,
    ) -> Signal:
        closes = [c.close for c in candles]
        if len(closes) < self.min_confirmed_bars():
            return Signal(
                action=SignalAction.HOLD,
                reason="Not enough confirmed candles",
                price=closes[-1] if closes else 0.0,
                explanation_code=explanation_code_for(
                    SignalAction.HOLD, enough_bars=False, indicators_ready=False
                ),
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                conditions=conditions_for_signal(
                    self.settings,
                    action=SignalAction.HOLD,
                    cross_up=None,
                    cross_down=None,
                    rsi_value=None,
                    indicators_ready=False,
                    enough_bars=False,
                ),
            )

        fast = ema(closes, self.settings.ema_fast)
        slow = ema(closes, self.settings.ema_slow)
        rsi_vals = rsi(closes, self.settings.rsi_period)

        i = len(closes) - 1
        prev = i - 1
        last = candles[i]
        close_ms = candle_close_ms(last.start, interval)

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
                candle_start_ms=last.start,
                candle_close_ms=close_ms,
                explanation_code=explanation_code_for(
                    SignalAction.HOLD, enough_bars=True, indicators_ready=False
                ),
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                conditions=conditions_for_signal(
                    self.settings,
                    action=SignalAction.HOLD,
                    cross_up=None,
                    cross_down=None,
                    rsi_value=None,
                    indicators_ready=False,
                    enough_bars=True,
                ),
            )

        f0, f1 = fast[prev], fast[i]
        s0, s1 = slow[prev], slow[i]
        r = rsi_vals[i]
        price = closes[i]

        cross_up = f0 <= s0 and f1 > s1
        cross_down = f0 >= s0 and f1 < s1

        def _sid(action: SignalAction) -> str:
            return build_signal_id(
                symbol=symbol,
                category=category,
                interval=interval,
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                candle_close_ms=close_ms,
                config_id=self.config_id,
                action=action.value,
            )

        if cross_up and r < self.settings.rsi_overbought:
            action = SignalAction.BUY
            return Signal(
                action=action,
                reason=(
                    f"EMA{self.settings.ema_fast} crossed above "
                    f"EMA{self.settings.ema_slow}, RSI={r:.1f}"
                ),
                price=price,
                ema_fast=f1,
                ema_slow=s1,
                rsi=r,
                candle_start_ms=last.start,
                candle_close_ms=close_ms,
                signal_id=_sid(action),
                explanation_code=explanation_code_for(
                    action, enough_bars=True, indicators_ready=True
                ),
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                conditions=conditions_for_signal(
                    self.settings,
                    action=action,
                    cross_up=True,
                    cross_down=False,
                    rsi_value=r,
                    indicators_ready=True,
                    enough_bars=True,
                ),
            )

        if cross_down and r > self.settings.rsi_oversold:
            action = SignalAction.SELL
            return Signal(
                action=action,
                reason=(
                    f"EMA{self.settings.ema_fast} crossed below "
                    f"EMA{self.settings.ema_slow}, RSI={r:.1f}"
                ),
                price=price,
                ema_fast=f1,
                ema_slow=s1,
                rsi=r,
                candle_start_ms=last.start,
                candle_close_ms=close_ms,
                signal_id=_sid(action),
                explanation_code=explanation_code_for(
                    action, enough_bars=True, indicators_ready=True
                ),
                strategy_id=self.strategy_id,
                strategy_version=self.strategy_version,
                conditions=conditions_for_signal(
                    self.settings,
                    action=action,
                    cross_up=False,
                    cross_down=True,
                    rsi_value=r,
                    indicators_ready=True,
                    enough_bars=True,
                ),
            )

        return Signal(
            action=SignalAction.HOLD,
            reason=f"No cross (EMA {f1:.6g}/{s1:.6g}, RSI={r:.1f})",
            price=price,
            ema_fast=f1,
            ema_slow=s1,
            rsi=r,
            candle_start_ms=last.start,
            candle_close_ms=close_ms,
            signal_id="",
            explanation_code=explanation_code_for(
                SignalAction.HOLD, enough_bars=True, indicators_ready=True
            ),
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            conditions=conditions_for_signal(
                self.settings,
                action=SignalAction.HOLD,
                cross_up=False,
                cross_down=False,
                rsi_value=r,
                indicators_ready=True,
                enough_bars=True,
            ),
        )
