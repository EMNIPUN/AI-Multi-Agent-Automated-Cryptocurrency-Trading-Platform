"""Local paper trading broker — simulation only; default OFF in application wiring."""

from agent.paper.broker import BrokerResult, PaperBroker, PaperSignalInput
from agent.paper.config import PaperBrokerConfig
from agent.paper.equity import EquitySnapshot, ValuationStatus, reconcile_equity
from agent.paper.integration import (
    PAPER_BROKER_AUTO_ATTACH,
    PAPER_PORTFOLIO_RISK_ENABLED,
    candle_from_market,
    decision_to_paper_signal,
    portfolio_risk_aligned_with_broker,
    submit_decision_to_paper,
    submit_decision_with_portfolio_risk,
)
from agent.paper.models import PaperCandle, PaperOrder, PaperPosition, PaperSession
from agent.paper.read_store import PaperDbUnavailable, PaperReadStore
from agent.paper.risk import (
    PortfolioRiskResult,
    PortfolioRiskVerdict,
    ProposedEntry,
    evaluate_portfolio_entry,
)
from agent.paper.risk_config import PortfolioRiskConfig
from agent.paper.store import PaperStore

__all__ = [
    "PAPER_BROKER_AUTO_ATTACH",
    "PAPER_PORTFOLIO_RISK_ENABLED",
    "BrokerResult",
    "EquitySnapshot",
    "PaperBroker",
    "PaperBrokerConfig",
    "PaperCandle",
    "PaperDbUnavailable",
    "PaperOrder",
    "PaperPosition",
    "PaperReadStore",
    "PaperSession",
    "PaperSignalInput",
    "PaperStore",
    "PortfolioRiskConfig",
    "PortfolioRiskResult",
    "PortfolioRiskVerdict",
    "ProposedEntry",
    "ValuationStatus",
    "candle_from_market",
    "decision_to_paper_signal",
    "evaluate_portfolio_entry",
    "portfolio_risk_aligned_with_broker",
    "reconcile_equity",
    "submit_decision_to_paper",
    "submit_decision_with_portfolio_risk",
]
