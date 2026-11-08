"""Portfolio risk configuration — paper simulation only; not live advice."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PortfolioRiskConfig:
    """
    Conservative local paper portfolio limits.

    Percent denominators (unless noted):
    - per-trade risk: marked_equity
    - gross exposure: marked_equity
    - daily loss: UTC-day start marked equity
    - drawdown: historical peak marked equity
    Currency: USDT (virtual).
    """

    max_risk_fraction_per_trade: Decimal = Decimal("0.01")
    max_open_positions: int = 3
    max_gross_exposure_fraction: Decimal = Decimal("0.60")
    max_daily_loss_fraction: Decimal = Decimal("0.03")
    max_drawdown_fraction: Decimal = Decimal("0.10")
    min_net_risk_reward: Decimal = Decimal("1.5")
    one_position_per_symbol: bool = True
    allow_short: bool = False
    allow_leverage: bool = False
    # Floor quantity to this step; never round up.
    quantity_step: Decimal = Decimal("0.00000001")
    # Only spot-like categories may open longs under portfolio risk.
    allowed_entry_categories: tuple[str, ...] = ("spot",)
    # Fee/slippage must match PaperBrokerConfig when used together.
    fee_rate: Decimal = Decimal("0.001")
    slippage_bps: Decimal = Decimal("5")
    # If True, missing/partial marks → DATA_UNAVAILABLE (no fabricated capacity).
    require_valid_marks_for_entries: bool = True

    def to_dict(self) -> dict:
        out = asdict(self)
        for k, v in list(out.items()):
            if isinstance(v, Decimal):
                out[k] = str(v)
        return out
