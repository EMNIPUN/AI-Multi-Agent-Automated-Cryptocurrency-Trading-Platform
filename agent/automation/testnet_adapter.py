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

    Mutating calls require TESTNET_ORDER_SUBMISSION_APPROVED (+ dual mode gates).
    Never builds a mainnet write client. LIVE remains a separate denied path.
    """

    environment = AdapterEnvironment.TESTNET

    def __init__(self, session: Any) -> None:
        gates = get_automation_gates()
        if not gates.bybit_testnet_env or gates.bybit_demo_env:
            raise AutomationGateError("real_adapter_requires_bybit_testnet_not_demo")
        if gates.mainnet_trading_enabled:
            raise AutomationGateError("mainnet_flag_blocks_adapter")
        self._session = session

    def _ret(self, raw: dict[str, Any]) -> dict[str, Any]:
        if int(raw.get("retCode", -1)) != 0:
            raise RuntimeError(f"bybit_error:{raw.get('retCode')}:{raw.get('retMsg')}")
        result = raw.get("result")
        return result if isinstance(result, dict) else {}

    def get_balance(self) -> BalanceSnapshot:
        raw = self._session.get_wallet_balance(accountType="UNIFIED")
        result = self._ret(raw)
        lists = result.get("list") or []
        row = lists[0] if lists else {}
        coins = row.get("coin") or []
        usdt = next((c for c in coins if str(c.get("coin") or "").upper() == "USDT"), None)
        equity = float(row.get("totalEquity") or (usdt or {}).get("equity") or 0.0)
        available = float(
            (usdt or {}).get("availableToWithdraw")
            or (usdt or {}).get("walletBalance")
            or row.get("totalAvailableBalance")
            or 0.0
        )
        return BalanceSnapshot(total_equity=equity, available_balance=available, environment="testnet")

    def get_instrument(self, *, category: str, symbol: str) -> InstrumentConstraints:
        raw = self._session.get_instruments_info(category=category, symbol=symbol.upper())
        result = self._ret(raw)
        rows = result.get("list") or []
        if not rows:
            raise KeyError(f"instrument_unknown:{category}:{symbol}")
        info = rows[0]
        lot = info.get("lotSizeFilter") or {}
        price = info.get("priceFilter") or {}
        lev = info.get("leverageFilter") or {}
        return InstrumentConstraints(
            symbol=symbol.upper(),
            category=category,
            min_order_qty=float(lot.get("minOrderQty") or 0.0),
            qty_step=float(lot.get("qtyStep") or 0.0),
            min_order_amt=float(lot.get("minNotionalValue") or lot.get("minOrderAmt") or 0.0),
            tick_size=float(price.get("tickSize") or 0.0),
            max_leverage=float(lev.get("maxLeverage")) if lev.get("maxLeverage") else None,
        )

    def place_order(self, **kwargs: Any) -> OrderAck:
        MockBybitTestnetAdapter._assert_submission_gate()
        assert_segment_allowed(str(kwargs.get("category") or "linear"))
        link = str(kwargs.get("orderLinkId") or kwargs.get("client_order_id") or "")
        if not link:
            raise ValueError("client_order_id_required")
        payload = {
            "category": kwargs.get("category", "linear"),
            "symbol": str(kwargs.get("symbol") or "").upper(),
            "side": kwargs.get("side"),
            "orderType": kwargs.get("orderType") or kwargs.get("order_type") or "Market",
            "qty": str(kwargs.get("qty")),
            "orderLinkId": link,
            "timeInForce": kwargs.get("timeInForce") or "GTC",
        }
        if kwargs.get("price") is not None:
            payload["price"] = str(kwargs["price"])
        raw = self._session.place_order(**payload)
        result = self._ret(raw)
        return OrderAck(
            client_order_id=link,
            exchange_order_id=str(result.get("orderId") or "") or None,
            status="Accepted",
            raw={**result, "retCode": 0},
            acknowledged_at_ms=int(time.time() * 1000),
        )

    def cancel_order(self, **kwargs: Any) -> OrderAck:
        MockBybitTestnetAdapter._assert_submission_gate()
        link = str(kwargs.get("orderLinkId") or "")
        payload = {
            "category": kwargs.get("category", "linear"),
            "symbol": str(kwargs.get("symbol") or "").upper(),
            "orderLinkId": link,
        }
        if kwargs.get("orderId"):
            payload["orderId"] = kwargs["orderId"]
        raw = self._session.cancel_order(**payload)
        result = self._ret(raw)
        return OrderAck(
            client_order_id=link,
            exchange_order_id=str(result.get("orderId") or "") or None,
            status="Cancelled",
            raw=result,
            acknowledged_at_ms=int(time.time() * 1000),
        )

    def get_order(self, **kwargs: Any) -> dict[str, Any]:
        raw = self._session.get_open_orders(
            category=kwargs.get("category", "linear"),
            symbol=str(kwargs.get("symbol") or "").upper(),
            orderLinkId=kwargs.get("orderLinkId"),
            orderId=kwargs.get("orderId"),
        )
        result = self._ret(raw)
        rows = result.get("list") or []
        if not rows:
            return {"orderStatus": "Unknown", "orderLinkId": kwargs.get("orderLinkId")}
        return dict(rows[0])

    def list_fills(self, **kwargs: Any) -> list[FillRecord]:
        raw = self._session.get_executions(
            category=kwargs.get("category", "linear"),
            symbol=str(kwargs.get("symbol") or "").upper(),
            orderId=kwargs.get("order_id"),
        )
        result = self._ret(raw)
        out: list[FillRecord] = []
        for row in result.get("list") or []:
            out.append(
                FillRecord(
                    exec_id=str(row.get("execId") or ""),
                    order_id=str(row.get("orderId") or ""),
                    qty=float(row.get("execQty") or 0.0),
                    price=float(row.get("execPrice") or 0.0),
                    fee=float(row.get("execFee") or 0.0),
                    is_maker=bool(row.get("isMaker")),
                )
            )
        return out

    def get_position(self, *, category: str, symbol: str) -> PositionView:
        raw = self._session.get_positions(category=category, symbol=symbol.upper())
        result = self._ret(raw)
        rows = result.get("list") or []
        if not rows:
            return PositionView(symbol.upper(), category, 0.0, "Flat", None, None)
        row = rows[0]
        size = float(row.get("size") or 0.0)
        side = str(row.get("side") or "Flat")
        if size == 0:
            side = "Flat"
        return PositionView(
            symbol=symbol.upper(),
            category=category,
            size=size,
            side=side,
            avg_price=float(row["avgPrice"]) if row.get("avgPrice") not in (None, "") else None,
            unrealised_pnl=float(row["unrealisedPnl"]) if row.get("unrealisedPnl") not in (None, "") else None,
            stop_loss=str(row["stopLoss"]) if row.get("stopLoss") not in (None, "") else None,
            take_profit=str(row["takeProfit"]) if row.get("takeProfit") not in (None, "") else None,
        )

    def set_trading_stop(self, spec: ProtectiveOrderSpec) -> dict[str, Any]:
        MockBybitTestnetAdapter._assert_submission_gate()
        raw = self._session.set_trading_stop(
            category=spec.category,
            symbol=spec.symbol.upper(),
            stopLoss=spec.stop_loss,
            takeProfit=spec.take_profit,
            positionIdx=spec.position_idx,
        )
        return self._ret(raw)


def assert_segment_allowed(category: str) -> MarketSegment:
    seg = MarketSegment(category)
    gates = get_automation_gates()
    if seg is MarketSegment.LINEAR and not gates.linear_auto_exec_allowed:
        raise AutomationGateError("linear_auto_execution_disabled")
    if seg is MarketSegment.SPOT and not gates.spot_auto_exec_allowed:
        # Spot also requires order_submission_allowed; callers may still plan.
        pass
    return seg
