"""Paper broker configuration — simulated costs only; not live Bybit fee tiers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PaperBrokerConfig:
    """Conservative synthetic defaults for local simulation."""

    initial_balance: Decimal = Decimal("1000")
    fee_rate: Decimal = Decimal("0.001")  # 10 bps each side — synthetic
    slippage_bps: Decimal = Decimal("5")  # 5 bps adverse
    max_open_positions: int = 1
    max_total_exposure: Decimal = Decimal("1000")  # notional sum of opens
    one_position_per_symbol: bool = True
    allow_short: bool = False  # MVP: longs only; SELL closes long
    currency: str = "USDT"
    schema_version: int = 2

    def to_dict(self) -> dict:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, Decimal):
                d[k] = str(v)
        return d


def d(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
