"""
Explicit paper-broker adapter.

NOT wired into default SignalPipeline / FastAPI / auto_engine.
Callers must opt in. Never interprets execution_allowed as live permission.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from agent.paper.broker import BrokerResult, PaperBroker, PaperSignalInput
from agent.paper.config import PaperBrokerConfig, d
from agent.paper.models import PaperCandle
from agent.paper.risk_config import PortfolioRiskConfig


def decision_to_paper_signal(decision: Any) -> PaperSignalInput | None:
    """
    Map a CoordinatorDecision-like object to PaperSignalInput.

    Returns None when mandatory broker fields are missing (reject rather than guess).
    """
    decision_id = getattr(decision, "decision_id", None)
    if not decision_id:
        return None

    action = getattr(decision, "action", None)
    action_s = action.value if hasattr(action, "value") else str(action or "")

    risk = getattr(decision, "risk", None)
    verdict = getattr(risk, "verdict", None) if risk is not None else None
    verdict_s = verdict.value if hasattr(verdict, "value") else str(verdict or "")

    levels = getattr(decision, "levels", None)
    entry = getattr(levels, "entry", None) if levels is not None else None
    stop = None
    tp = None
    if levels is not None:
        stop = getattr(levels, "stop_loss", None)
        if stop is None:
            stop = getattr(levels, "stop", None)
        tp = getattr(levels, "take_profit", None)

    notional = getattr(risk, "position_notional", None) if risk is not None else None
    candle_start = getattr(decision, "candle_start_ms", None)
    if candle_start is None:
        candle_start = getattr(decision, "bar_start_ms", None)
    if candle_start is None:
        market = getattr(decision, "market", None)
        if market is not None:
            candle_start = getattr(market, "newest_close_ms", None)

    created_ms = getattr(decision, "created_ms", None)
    if created_ms is None:
        created_ms = getattr(decision, "timestamp_ms", None)
    if created_ms is None:
        return None

    symbol = getattr(decision, "symbol", None)
    category = getattr(decision, "category", None)
    if not symbol or not category:
        return None

    interval = str(getattr(decision, "interval", "15") or "15")

    return PaperSignalInput(
        signal_id=str(decision_id),
        symbol=str(symbol),
        category=str(category),
        action=str(action_s).upper(),
        risk_verdict=str(verdict_s).upper(),
        entry_price=d(entry) if entry is not None else None,
        stop_loss=d(stop) if stop is not None else None,
        take_profit=d(tp) if tp is not None else None,
        position_notional=d(notional) if notional is not None else None,
        signal_candle_start_ms=int(candle_start) if candle_start is not None else None,
        created_ms=int(created_ms),
        interval=interval,
    )


def submit_decision_to_paper(
    broker: PaperBroker,
    *,
    session_id: str,
    decision: Any,
) -> BrokerResult:
    """Opt-in bridge: persist-eligible decision → paper order path."""
    signal = decision_to_paper_signal(decision)
    if signal is None:
        return BrokerResult(False, "MISSING_BROKER_FIELDS")
    return broker.submit_signal(session_id=session_id, signal=signal)


def candle_from_market(
    *,
    start_ms: int,
    open_: float | Decimal,
    high: float | Decimal,
    low: float | Decimal,
    close: float | Decimal,
    volume: float | Decimal = 0,
    symbol: str,
    interval: str = "15",
) -> PaperCandle:
    return PaperCandle(
        start_ms=int(start_ms),
        open=d(open_),
        high=d(high),
        low=d(low),
        close=d(close),
        volume=d(volume),
        symbol=symbol,
        interval=interval,
    )


# Feature flag documentation constants — default application must keep paper OFF.
PAPER_BROKER_AUTO_ATTACH = False
PAPER_PORTFOLIO_RISK_ENABLED = False  # opt-in only; never auto-wired into SignalPipeline


def portfolio_risk_aligned_with_broker(
    broker_config: PaperBrokerConfig,
    *,
    max_open_positions: int = 3,
    max_gross_exposure_fraction: str = "0.60",
) -> PortfolioRiskConfig:
    """Build portfolio risk config using the same fee/slippage as the paper broker."""
    return PortfolioRiskConfig(
        fee_rate=broker_config.fee_rate,
        slippage_bps=broker_config.slippage_bps,
        max_open_positions=max_open_positions,
        max_gross_exposure_fraction=d(max_gross_exposure_fraction),
        one_position_per_symbol=broker_config.one_position_per_symbol,
        allow_short=False,
        allow_leverage=False,
    )


def submit_decision_with_portfolio_risk(
    broker: PaperBroker,
    *,
    session_id: str,
    decision: Any,
    signal_risk_verdict: str | None = None,
) -> BrokerResult:
    """
    Opt-in adapter: SignalPipeline → paper portfolio risk → broker.

    - Existing signal risk VETO/BLOCKED/HALTED is authoritative (never overridden).
    - Requires broker.portfolio_risk to be configured.
    - Does not enable PAPER_BROKER_AUTO_ATTACH.
    - Does not change execution_allowed semantics.
    """
    if not PAPER_PORTFOLIO_RISK_ENABLED and broker.portfolio_risk is None:
        # Even when global flag is false, explicit broker.portfolio_risk allows tests/demo.
        pass

    signal = decision_to_paper_signal(decision)
    if signal is None:
        return BrokerResult(False, "MISSING_BROKER_FIELDS")

    verdict = (signal_risk_verdict or signal.risk_verdict or "").upper()
    if verdict in {"VETO", "VETOED", "BLOCKED", "HALTED"}:
        return BrokerResult(
            False,
            "SIGNAL_RISK_VETO_AUTHORITATIVE",
            detail={"signal_risk_verdict": verdict},
        )
    if verdict != "APPROVED":
        return BrokerResult(False, "SIGNAL_RISK_NOT_APPROVED")

    if broker.portfolio_risk is None:
        return BrokerResult(False, "PORTFOLIO_RISK_NOT_CONFIGURED")

    # Ensure signal carries APPROVED for broker gate; portfolio sizes inside broker.
    signal = PaperSignalInput(
        **{
            **signal.__dict__,
            "risk_verdict": "APPROVED",
            "action": signal.action,
        }
    )
    return broker.submit_signal(session_id=session_id, signal=signal)
