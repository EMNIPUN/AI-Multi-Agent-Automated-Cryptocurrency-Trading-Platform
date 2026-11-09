"""Bounded autonomous PAPER session authorization.

One operator start authorizes continuous paper trading for a fixed symbol,
capital, risk budget, and duration. No per-trade chat approval is required.
Live and testnet remain unreachable from this object.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Literal


@dataclass(frozen=True)
class PaperSessionAuthorization:
    mode: Literal["PAPER"] = "PAPER"
    symbol: str = "HYPEUSDT"
    category: str = "linear"
    interval: str = "15"
    capital_usdt: Decimal = Decimal("5")
    risk_fraction: Decimal = Decimal("0.01")
    duration_hours: int = 48
    per_trade_approval: bool = False
    live_orders: bool = False
    testnet_orders: bool = False
    started_at_ms: int = 0
    expires_at_ms: int = 0
    strategy_version: str = "ema_rsi"
    profit_target_is_not_a_requirement: bool = True

    def to_dict(self) -> dict[str, Any]:
        body = asdict(self)
        body["capital_usdt"] = str(self.capital_usdt)
        body["risk_fraction"] = str(self.risk_fraction)
        body["risk_budget_usdt"] = str(self.capital_usdt * self.risk_fraction)
        body["execution_mode"] = "PAPER"
        body["autonomous"] = not self.per_trade_approval
        return body

    def expired(self, now_ms: int) -> bool:
        return self.expires_at_ms > 0 and int(now_ms) >= int(self.expires_at_ms)


def default_paper_authorization(*, now_ms: int = 0) -> PaperSessionAuthorization:
    duration_hours = 48
    started = int(now_ms or 0)
    expires = started + duration_hours * 3_600_000 if started > 0 else 0
    return PaperSessionAuthorization(started_at_ms=started, expires_at_ms=expires)


def authorization_from_dict(raw: dict[str, Any] | None, *, now_ms: int = 0) -> PaperSessionAuthorization:
    data = raw or {}
    base = default_paper_authorization(now_ms=now_ms)
    symbol = str(data.get("symbol") or base.symbol).upper()
    category = str(data.get("category") or base.category).lower()
    interval = str(data.get("interval") or base.interval)
    capital = Decimal(str(data.get("capital_usdt") or base.capital_usdt))
    risk = Decimal(str(data.get("risk_fraction") or base.risk_fraction))
    duration = int(data.get("duration_hours") or base.duration_hours)
    started = int(data.get("started_at_ms") or now_ms or 0)
    expires = int(data.get("expires_at_ms") or (started + duration * 3_600_000 if started else 0))
    return PaperSessionAuthorization(
        mode="PAPER",
        symbol=symbol,
        category=category if category in {"linear", "spot"} else "linear",
        interval=interval,
        capital_usdt=capital if capital > 0 else base.capital_usdt,
        risk_fraction=risk if risk > 0 else base.risk_fraction,
        duration_hours=max(1, duration),
        per_trade_approval=False,
        live_orders=False,
        testnet_orders=False,
        started_at_ms=started,
        expires_at_ms=expires,
        strategy_version=str(data.get("strategy_version") or base.strategy_version),
        profit_target_is_not_a_requirement=True,
    )
