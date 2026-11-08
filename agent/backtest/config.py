"""Immutable validated backtest configuration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from agent.candle_time import assert_supported_interval
from agent.multi_agent.config import STRATEGY_VERSION, SignalPipelineConfig, config_hash
from agent.paper.config import PaperBrokerConfig, d
from agent.paper.risk_config import PortfolioRiskConfig


BACKTEST_ENGINE_VERSION = "68A.1.0"
PERFORMANCE_LABEL = "HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE"


class RiskMode(str, Enum):
    """Isolated backtest risk mode — does not flip global PAPER_* flags."""

    SIGNAL_ONLY = "signal_only"
    PORTFOLIO = "portfolio"


class DataSourceKind(str, Enum):
    FIXTURE_FILE = "fixture_file"
    INLINE = "inline"
    BYBIT_PUBLIC = "bybit_public"  # optional offline-cached public path only


@dataclass(frozen=True)
class BacktestConfig:
    symbol: str = "BTCUSDT"
    market_type: str = "spot"  # paper portfolio risk allows spot entries
    interval: str = "15"
    start_ms: int | None = None
    end_ms: int | None = None
    initial_capital: Decimal = Decimal("10000")
    fee_rate: Decimal = Decimal("0.001")
    slippage_bps: Decimal = Decimal("5")
    risk_mode: RiskMode = RiskMode.SIGNAL_ONLY
    grace_ms: int = 2_000
    min_confirmed_bars: int | None = None  # default: pipeline config
    data_source: DataSourceKind = DataSourceKind.INLINE
    dataset_path: str | None = None
    dataset_hash: str | None = None  # filled from loaded dataset when omitted
    seed: int | None = None  # reserved; engine itself is non-random
    pipeline: SignalPipelineConfig = field(default_factory=SignalPipelineConfig)
    portfolio_risk: PortfolioRiskConfig | None = None
    force_close_at_end: bool = False  # explicitly labeled terminal liquidation (off)
    engine_version: str = BACKTEST_ENGINE_VERSION

    def __post_init__(self) -> None:
        assert_supported_interval(self.interval)
        if not self.symbol.strip():
            raise ValueError("symbol required")
        if self.market_type not in {"spot", "linear"}:
            raise ValueError("market_type must be spot or linear")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if self.fee_rate < 0 or self.slippage_bps < 0:
            raise ValueError("fee_rate and slippage_bps must be non-negative")
        if self.start_ms is not None and self.end_ms is not None and self.start_ms > self.end_ms:
            raise ValueError("start_ms cannot exceed end_ms")
        if self.grace_ms < 0:
            raise ValueError("grace_ms must be non-negative")
        if self.force_close_at_end:
            raise ValueError(
                "force_close_at_end is not implemented; leave False "
                "(open positions remain open at dataset end)"
            )
        if self.risk_mode is RiskMode.PORTFOLIO and self.market_type != "spot":
            raise ValueError(
                "portfolio risk mode requires market_type=spot "
                "(PortfolioRiskConfig.allowed_entry_categories)"
            )

    def effective_min_bars(self) -> int:
        if self.min_confirmed_bars is not None:
            return int(self.min_confirmed_bars)
        return int(self.pipeline.min_confirmed_bars)

    def broker_config(self) -> PaperBrokerConfig:
        # Exposure ceiling is intentionally above cash so the hard gate is
        # available balance (plus the cash-cap in execution_adapter). A ceiling
        # equal to capital alone rejected risk-sized notionals with MAX_EXPOSURE
        # before the cash check could run.
        return PaperBrokerConfig(
            initial_balance=d(self.initial_capital),
            fee_rate=d(self.fee_rate),
            slippage_bps=d(self.slippage_bps),
            max_open_positions=1 if self.risk_mode is RiskMode.SIGNAL_ONLY else 3,
            max_total_exposure=d(self.initial_capital) * Decimal("10"),
            one_position_per_symbol=True,
            allow_short=False,
            currency="USDT",
        )

    def resolved_portfolio_risk(self) -> PortfolioRiskConfig | None:
        if self.risk_mode is not RiskMode.PORTFOLIO:
            return None
        if self.portfolio_risk is not None:
            return self.portfolio_risk
        bc = self.broker_config()
        return PortfolioRiskConfig(
            fee_rate=bc.fee_rate,
            slippage_bps=bc.slippage_bps,
            max_open_positions=3,
            max_gross_exposure_fraction=Decimal("0.60"),
            one_position_per_symbol=True,
            allow_short=False,
            allow_leverage=False,
            allowed_entry_categories=("spot",),
        )

    def to_effective_dict(self, *, dataset_hash: str) -> dict[str, Any]:
        pipe = self.pipeline
        return {
            "engine_version": self.engine_version,
            "agent_pipeline_version": pipe.strategy_version or STRATEGY_VERSION,
            "pipeline_config_hash": config_hash(pipe),
            "symbol": self.symbol,
            "market_type": self.market_type,
            "interval": self.interval,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "initial_capital": str(d(self.initial_capital)),
            "fee_rate": str(d(self.fee_rate)),
            "slippage_bps": str(d(self.slippage_bps)),
            "risk_mode": self.risk_mode.value,
            "grace_ms": self.grace_ms,
            "min_confirmed_bars": self.effective_min_bars(),
            "data_source": self.data_source.value,
            "dataset_path": self.dataset_path,
            "dataset_hash": dataset_hash,
            "seed": self.seed,
            "force_close_at_end": self.force_close_at_end,
            "portfolio_risk": (
                self.resolved_portfolio_risk().to_dict()
                if self.resolved_portfolio_risk() is not None
                else None
            ),
            "pipeline": {
                "strategy_version": pipe.strategy_version,
                "min_confirmed_bars": pipe.min_confirmed_bars,
                "buy_threshold": pipe.buy_threshold,
                "sell_threshold": pipe.sell_threshold,
                "min_market_quality": pipe.min_market_quality,
                "weights": asdict(pipe.weights.normalized()),
                "risk": asdict(pipe.risk),
            },
            "performance_label": PERFORMANCE_LABEL,
        }


def effective_config_hash(effective: dict[str, Any]) -> str:
    raw = json.dumps(effective, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
