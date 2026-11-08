"""Isolated portfolio risk wiring for backtests — does not mutate global flags."""

from __future__ import annotations

from agent.backtest.config import BacktestConfig, RiskMode
from agent.paper.broker import PaperBroker
from agent.paper.config import PaperBrokerConfig
from agent.paper.integration import (
    PAPER_BROKER_AUTO_ATTACH,
    PAPER_PORTFOLIO_RISK_ENABLED,
)
from agent.paper.risk_config import PortfolioRiskConfig
from agent.paper.store import PaperStore


def assert_safety_defaults() -> None:
    if PAPER_BROKER_AUTO_ATTACH is not False:
        raise RuntimeError("PAPER_BROKER_AUTO_ATTACH must remain False")
    if PAPER_PORTFOLIO_RISK_ENABLED is not False:
        raise RuntimeError("PAPER_PORTFOLIO_RISK_ENABLED must remain False")


def build_broker(store: PaperStore, config: BacktestConfig) -> PaperBroker:
    assert_safety_defaults()
    broker_cfg: PaperBrokerConfig = config.broker_config()
    portfolio: PortfolioRiskConfig | None = config.resolved_portfolio_risk()
    # Inject portfolio risk only for this isolated broker instance.
    return PaperBroker(store, broker_cfg, portfolio_risk=portfolio)


def portfolio_enabled(config: BacktestConfig) -> bool:
    return config.risk_mode is RiskMode.PORTFOLIO
