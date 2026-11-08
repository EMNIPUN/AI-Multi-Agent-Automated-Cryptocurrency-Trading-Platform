"""
Phase 6A Bybit V5 Testnet trading adapter.

Strictly separate from:
- Public mainnet market-data clients
- BybitTestnetVerificationAdapter (credential verify only)
- Mainnet write sessions

Real order submission is refused until TESTNET_ORDER_SUBMISSION_APPROVED.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from agent.automation.modes import (
    AutomationGateError,
    MarketSegment,
    get_automation_gates,
)


class AdapterEnvironment(str, Enum):
    TESTNET = "testnet"
    MAINNET = "mainnet"  # construction must raise
    DEMO = "demo"  # rejected for auto-trading


@dataclass(frozen=True)
class InstrumentConstraints:
    symbol: str
    category: str
    min_order_qty: float
    qty_step: float
    min_order_amt: float
    tick_size: float
    max_leverage: float | None = None


@dataclass(frozen=True)
class BalanceSnapshot:
    total_equity: float
    available_balance: float
    coin: str = "USDT"
    environment: str = "testnet"


@dataclass(frozen=True)
class OrderAck:
    """Exchange acknowledgement — NOT proof of fill."""

    client_order_id: str
    exchange_order_id: str | None
    status: str
    raw: dict[str, Any] = field(default_factory=dict)
    acknowledged_at_ms: int = 0


@dataclass(frozen=True)
class FillRecord:
    exec_id: str
    order_id: str
    qty: float
    price: float
    fee: float
    is_maker: bool = False


@dataclass(frozen=True)
class PositionView:
    symbol: str
    category: str
    size: float
    side: str  # Buy/Sell/Flat
    avg_price: float | None
    unrealised_pnl: float | None
    stop_loss: str | None = None
    take_profit: str | None = None


@dataclass(frozen=True)
class ProtectiveOrderSpec:
    symbol: str
    category: str
    stop_loss: str | None
    take_profit: str | None
    position_idx: int = 0


class BybitTestnetTradingAdapter(Protocol):
    environment: AdapterEnvironment

    def get_balance(self) -> BalanceSnapshot: ...
    def get_instrument(self, *, category: str, symbol: str) -> InstrumentConstraints: ...
    def place_order(self, **kwargs: Any) -> OrderAck: ...
    def cancel_order(self, **kwargs: Any) -> OrderAck: ...
    def get_order(self, **kwargs: Any) -> dict[str, Any]: ...
    def list_fills(self, **kwargs: Any) -> list[FillRecord]: ...
    def get_position(self, *, category: str, symbol: str) -> PositionView: ...
    def set_trading_stop(self, spec: ProtectiveOrderSpec) -> dict[str, Any]: ...


class MockBybitTestnetAdapter:
    """Deterministic fixture adapter for offline tests — never hits network."""

    environment = AdapterEnvironment.TESTNET

    def __init__(self) -> None:
        self.orders: dict[str, dict[str, Any]] = {}
        self.fills: list[FillRecord] = []
        self.positions: dict[tuple[str, str], PositionView] = {}
        self.balance = BalanceSnapshot(10_000.0, 9_500.0)
        self.api_errors = 0
        self.place_calls = 0
        self.reject_next_stop = False
        self.ambiguous_next_place = False
        self.instruments = {
            ("spot", "BTCUSDT"): InstrumentConstraints(
                symbol="BTCUSDT",
                category="spot",
                min_order_qty=0.0001,
                qty_step=0.0001,
                min_order_amt=5.0,
                tick_size=0.1,
            ),
            ("linear", "BTCUSDT"): InstrumentConstraints(
                symbol="BTCUSDT",
                category="linear",
                min_order_qty=0.001,
                qty_step=0.001,
                min_order_amt=5.0,
                tick_size=0.1,
                max_leverage=50.0,
            ),
        }

    def get_balance(self) -> BalanceSnapshot:
        return self.balance

    def get_instrument(self, *, category: str, symbol: str) -> InstrumentConstraints:
        key = (category, symbol.upper())
        if key not in self.instruments:
            raise KeyError(f"instrument_unknown:{category}:{symbol}")
        return self.instruments[key]

    def place_order(self, **kwargs: Any) -> OrderAck:
        self._assert_submission_gate()
        self.place_calls += 1
        if self.ambiguous_next_place:
            self.ambiguous_next_place = False
            raise TimeoutError("mock_ambiguous_timeout")
        link = str(kwargs.get("orderLinkId") or kwargs.get("client_order_id") or "")
        if not link:
            raise ValueError("client_order_id_required")
        if link in self.orders:
            # Idempotent ack replay
            prev = self.orders[link]
            return OrderAck(
                client_order_id=link,
                exchange_order_id=prev.get("orderId"),
                status="Accepted",
                raw=prev,
                acknowledged_at_ms=int(time.time() * 1000),
            )
        oid = f"mock-{uuid.uuid4().hex[:12]}"
        row = {
            "orderId": oid,
            "orderLinkId": link,
            "symbol": kwargs.get("symbol"),
            "side": kwargs.get("side"),
            "qty": kwargs.get("qty"),
            "category": kwargs.get("category", "spot"),
            "orderStatus": "New",
            "cumExecQty": "0",
        }
        self.orders[link] = row
        return OrderAck(
            client_order_id=link,
            exchange_order_id=oid,
            status="Accepted",
            raw=row,
            acknowledged_at_ms=int(time.time() * 1000),
        )

    def cancel_order(self, **kwargs: Any) -> OrderAck:
        self._assert_submission_gate()
        link = str(kwargs.get("orderLinkId") or "")
        row = self.orders.get(link, {})
        if row:
            row["orderStatus"] = "Cancelled"
        return OrderAck(
            client_order_id=link,
            exchange_order_id=row.get("orderId"),
            status="Cancelled",
            raw=row,
            acknowledged_at_ms=int(time.time() * 1000),
        )

    def get_order(self, **kwargs: Any) -> dict[str, Any]:
        link = str(kwargs.get("orderLinkId") or "")
        if link not in self.orders:
            return {"orderStatus": "Unknown", "orderLinkId": link}
        return dict(self.orders[link])

    def list_fills(self, **kwargs: Any) -> list[FillRecord]:
        oid = kwargs.get("order_id")
        return [f for f in self.fills if oid is None or f.order_id == oid]

    def get_position(self, *, category: str, symbol: str) -> PositionView:
        return self.positions.get(
            (category, symbol.upper()),
            PositionView(symbol.upper(), category, 0.0, "Flat", None, None),
        )

    def set_trading_stop(self, spec: ProtectiveOrderSpec) -> dict[str, Any]:
        self._assert_submission_gate()
        if self.reject_next_stop:
            self.reject_next_stop = False
            raise RuntimeError("mock_stop_rejected")
        key = (spec.category, spec.symbol.upper())
        pos = self.get_position(category=spec.category, symbol=spec.symbol)
        self.positions[key] = PositionView(
            symbol=pos.symbol,
            category=pos.category,
            size=pos.size,
            side=pos.side,
            avg_price=pos.avg_price,
            unrealised_pnl=pos.unrealised_pnl,
            stop_loss=spec.stop_loss,
            take_profit=spec.take_profit,
        )
        return {"retCode": 0, "stopLoss": spec.stop_loss, "takeProfit": spec.take_profit}

    def simulate_full_fill(self, *, client_order_id: str, price: float) -> FillRecord:
        row = self.orders[client_order_id]
        qty = float(row["qty"])
        fill = FillRecord(
            exec_id=f"exec-{uuid.uuid4().hex[:10]}",
            order_id=str(row["orderId"]),
            qty=qty,
            price=price,
            fee=0.0,
        )
        self.fills.append(fill)
        row["orderStatus"] = "Filled"
        row["cumExecQty"] = str(qty)
        cat = str(row.get("category") or "spot")
        sym = str(row.get("symbol") or "").upper()
        side = str(row.get("side") or "Buy")
        self.positions[(cat, sym)] = PositionView(
            symbol=sym,
            category=cat,
            size=qty if side == "Buy" else -qty,
            side=side,
            avg_price=price,
            unrealised_pnl=0.0,
        )
        return fill

    @staticmethod
    def _assert_submission_gate() -> None:
        gates = get_automation_gates()
        if gates.mode.value == "MAINNET_TRADING" or gates.mainnet_trading_enabled:
            raise AutomationGateError("mainnet_execution_forbidden")
        if not gates.order_submission_allowed:
            raise AutomationGateError("testnet_order_submission_not_approved")


class RealBybitTestnetAdapter:
    """
    Live Testnet pybit wrapper — constructed only when env is Testnet.

    place_order still refuses until TESTNET_ORDER_SUBMISSION_APPROVED.
    Never builds a mainnet write client.
    """

    environment = AdapterEnvironment.TESTNET

    def __init__(self, session: Any) -> None:
        gates = get_automation_gates()
        if not gates.bybit_testnet_env or gates.bybit_demo_env:
            raise AutomationGateError("real_adapter_requires_bybit_testnet_not_demo")
        if gates.mainnet_trading_enabled:
            raise AutomationGateError("mainnet_flag_blocks_adapter")
        self._session = session

    def get_balance(self) -> BalanceSnapshot:
        # Read path may be used later under Testnet mode; still no orders here.
        raise NotImplementedError("real_balance_deferred_until_operator_connectivity_approval")

    def get_instrument(self, *, category: str, symbol: str) -> InstrumentConstraints:
        raise NotImplementedError("real_instrument_deferred")

    def place_order(self, **kwargs: Any) -> OrderAck:
        MockBybitTestnetAdapter._assert_submission_gate()
        # Even if gates open, Phase 6A stops before enabling this body without
        # a separate connectivity checklist approval.
        raise AutomationGateError(
            "real_testnet_place_order_blocked_pending_connectivity_approval"
        )

    def cancel_order(self, **kwargs: Any) -> OrderAck:
        raise AutomationGateError("real_testnet_cancel_blocked_pending_approval")

    def get_order(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("real_get_order_deferred")

    def list_fills(self, **kwargs: Any) -> list[FillRecord]:
        raise NotImplementedError("real_fills_deferred")

    def get_position(self, *, category: str, symbol: str) -> PositionView:
        raise NotImplementedError("real_position_deferred")

    def set_trading_stop(self, spec: ProtectiveOrderSpec) -> dict[str, Any]:
        raise AutomationGateError("real_testnet_stop_blocked_pending_approval")


def assert_segment_allowed(category: str) -> MarketSegment:
    seg = MarketSegment(category)
    gates = get_automation_gates()
    if seg is MarketSegment.LINEAR and not gates.linear_auto_exec_allowed:
        raise AutomationGateError("linear_auto_execution_disabled")
    if seg is MarketSegment.SPOT and not gates.spot_auto_exec_allowed:
        # Spot also requires order_submission_allowed; callers may still plan.
        pass
    return seg
