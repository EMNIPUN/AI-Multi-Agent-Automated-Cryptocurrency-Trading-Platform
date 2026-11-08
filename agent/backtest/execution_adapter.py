"""Paper broker simulation adapter — next-candle fills; no live orders."""

from __future__ import annotations

from typing import Any

from agent.market_data import Candle
from agent.multi_agent.types import CoordinatorDecision, DecisionAction, RiskVerdict
from agent.paper.broker import BrokerResult, PaperBroker, PaperSignalInput
from agent.paper.config import d
from agent.paper.integration import candle_from_market
from agent.paper.models import PaperCandle


def market_to_paper_candle(c: Candle, *, symbol: str, interval: str) -> PaperCandle:
    return candle_from_market(
        start_ms=int(c.start),
        open_=c.open,
        high=c.high,
        low=c.low,
        close=c.close,
        volume=c.volume,
        symbol=symbol,
        interval=interval,
    )


def decision_to_backtest_signal(
    decision: CoordinatorDecision,
    *,
    signal_candle_start_ms: int,
) -> PaperSignalInput | None:
    """
    Map CoordinatorDecision → PaperSignalInput.

    Always set signal_candle_start_ms to the decision bar *start* so the broker
    fills on the next candle open (65A). Do not use newest_close_ms as start.
    """
    if not decision.decision_id:
        return None
    action = decision.action.value if hasattr(decision.action, "value") else str(decision.action)
    verdict = (
        decision.risk.verdict.value
        if hasattr(decision.risk.verdict, "value")
        else str(decision.risk.verdict)
    )
    return PaperSignalInput(
        signal_id=str(decision.decision_id),
        symbol=str(decision.symbol),
        category=str(decision.category),
        action=str(action).upper(),
        risk_verdict=str(verdict).upper(),
        entry_price=d(decision.levels.entry) if decision.levels.entry is not None else None,
        stop_loss=d(decision.levels.stop_loss)
        if decision.levels.stop_loss is not None
        else None,
        take_profit=d(decision.levels.take_profit)
        if decision.levels.take_profit is not None
        else None,
        position_notional=d(decision.risk.position_notional)
        if decision.risk.position_notional is not None
        else None,
        signal_candle_start_ms=int(signal_candle_start_ms),
        created_ms=int(decision.timestamp_ms),
        interval=str(decision.interval),
    )


def is_actionable(decision: CoordinatorDecision) -> bool:
    if decision.action not in {DecisionAction.BUY, DecisionAction.SELL}:
        return False
    return decision.risk.verdict is RiskVerdict.APPROVED


def _cash_cap_signal(
    broker: PaperBroker, *, session_id: str, signal: PaperSignalInput
) -> PaperSignalInput:
    """
    Cap BUY notional to spendable cash (fee buffer).

    Signal risk sizes by stop distance and can request notionals above capital.
    Without a cap, the broker rejects every BUY with INSUFFICIENT_FUNDS /
    MAX_EXPOSURE and the backtest never exercises fills. Documented assumption:
    backtest execution cash-caps risk notional; it does not invent leverage.
    """
    if (signal.action or "").upper() != "BUY":
        return signal
    if signal.position_notional is None:
        return signal
    sess = broker.get_session(session_id)
    if sess is None:
        return signal
    # Match PaperBroker submit estimate: notional * slip_mult * (1 + fee_rate).
    fee = d(broker.config.fee_rate)
    slip_mult = d("1") + (d(broker.config.slippage_bps) / d("10000"))
    spendable = d(sess.available_balance)
    if spendable <= 0:
        return signal
    denom = slip_mult * (d("1") + fee)
    max_notional = spendable / denom if denom > 0 else spendable
    # Tiny buffer against Decimal quantization pushing est_cost over cash.
    max_notional = max_notional * d("0.999")
    if d(signal.position_notional) <= max_notional:
        return signal
    return PaperSignalInput(
        signal_id=signal.signal_id,
        symbol=signal.symbol,
        category=signal.category,
        action=signal.action,
        risk_verdict=signal.risk_verdict,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        position_notional=max_notional,
        signal_candle_start_ms=signal.signal_candle_start_ms,
        created_ms=signal.created_ms,
        interval=signal.interval,
    )


def submit_decision(
    broker: PaperBroker,
    *,
    session_id: str,
    decision: CoordinatorDecision,
    signal_candle_start_ms: int,
    use_portfolio_path: bool,
) -> BrokerResult:
    signal = decision_to_backtest_signal(
        decision, signal_candle_start_ms=signal_candle_start_ms
    )
    if signal is None:
        return BrokerResult(False, "MISSING_BROKER_FIELDS")
    if not is_actionable(decision):
        return BrokerResult(False, "NOT_ACTIONABLE")
    signal = _cash_cap_signal(broker, session_id=session_id, signal=signal)
    if use_portfolio_path:
        # Explicit portfolio_risk on broker is required; global flag stays False.
        if broker.portfolio_risk is None:
            return BrokerResult(False, "PORTFOLIO_RISK_NOT_CONFIGURED")
        return broker.submit_signal(session_id=session_id, signal=signal)
    return broker.submit_signal(session_id=session_id, signal=signal)


def process_market_candle(
    broker: PaperBroker,
    *,
    session_id: str,
    candle: Candle,
    symbol: str,
    interval: str,
) -> list[BrokerResult]:
    paper_c = market_to_paper_candle(candle, symbol=symbol, interval=interval)
    return broker.process_candle(
        session_id=session_id, candle=paper_c, interval=interval
    )


def broker_result_detail(r: BrokerResult) -> dict[str, Any]:
    return dict(r.detail or {})
