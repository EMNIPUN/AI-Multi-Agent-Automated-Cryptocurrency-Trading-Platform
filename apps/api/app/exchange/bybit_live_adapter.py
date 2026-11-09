"""Bybit LIVE execution adapter — MAINNET orders when operator env gates are armed.

Orchestrator chat never bypasses human Approve; it only calls this after
approve_live_trade. Default remains Denied when AGENT_ALLOW_LIVE / MAINNET flags
are off or Bybit is still on testnet/demo.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class LiveExecutionDisabled(RuntimeError):
    """Raised when LIVE mutate is not authorized or Bybit env is wrong."""

    def __init__(self, reason: str = "live_execution_disabled") -> None:
        super().__init__(reason)
        self.reason = reason


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def live_session_token_present() -> bool:
    return bool((os.getenv("CRYPTONOVA_LIVE_SESSION_TOKEN") or "").strip())


def live_session_token_fingerprint() -> str | None:
    raw = (os.getenv("CRYPTONOVA_LIVE_SESSION_TOKEN") or "").strip()
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def bybit_is_mainnet() -> bool:
    return (not _flag("BYBIT_TESTNET")) and (not _flag("BYBIT_DEMO"))


def live_mutate_allowed() -> bool:
    """Operator-armed MAINNET live mutate. Chat cannot set these flags."""
    if not bybit_is_mainnet():
        return False
    if not _flag("AGENT_ALLOW_LIVE"):
        return False
    if not _flag("MAINNET_TRADING_ENABLED"):
        return False
    # Optional session token — when set it must be present; when unset, dual flags suffice.
    token_required = _flag("CRYPTONOVA_LIVE_SESSION_TOKEN_REQUIRED")
    if token_required and not live_session_token_present():
        return False
    return True


class BybitLiveExecutionPort(Protocol):
    def fetch_balance(self) -> dict[str, Any]: ...

    def fetch_instrument(self, symbol: str) -> dict[str, Any]: ...

    def fetch_positions(self, symbol: str) -> dict[str, Any]: ...

    def place_order(self, **kwargs: Any) -> dict[str, Any]: ...

    def cancel_order(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_order_status(self, **kwargs: Any) -> dict[str, Any]: ...

    def place_protective_orders(self, **kwargs: Any) -> dict[str, Any]: ...

    def fetch_executions(self, **kwargs: Any) -> dict[str, Any]: ...

    def reconcile_position(self, symbol: str) -> dict[str, Any]: ...


def durable_client_order_id(*, symbol: str, side: str, intent_key: str) -> str:
    seed = f"{symbol}|{side}|{intent_key}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()[:24]
    return f"cnlive_{digest}"


@dataclass
class DeniedLiveExecutionAdapter:
    """Refuses every mutating LIVE call when gates are off."""

    reason: str = "live_execution_disabled"

    def _deny(self, op: str) -> dict[str, Any]:
        raise LiveExecutionDisabled(f"{self.reason}:{op}")

    def fetch_balance(self) -> dict[str, Any]:
        return {"ok": False, "error": self.reason, "live_orders": False, "execution_allowed": False}

    def fetch_instrument(self, symbol: str) -> dict[str, Any]:
        return {"ok": False, "symbol": symbol, "error": self.reason, "live_orders": False}

    def fetch_positions(self, symbol: str) -> dict[str, Any]:
        return {"ok": False, "symbol": symbol, "positions": [], "error": self.reason, "live_orders": False}

    def place_order(self, **kwargs: Any) -> dict[str, Any]:
        return self._deny("place_order")

    def cancel_order(self, **kwargs: Any) -> dict[str, Any]:
        return self._deny("cancel_order")

    def get_order_status(self, **kwargs: Any) -> dict[str, Any]:
        return {"ok": False, "error": self.reason, "live_orders": False}

    def place_protective_orders(self, **kwargs: Any) -> dict[str, Any]:
        return self._deny("place_protective_orders")

    def fetch_executions(self, **kwargs: Any) -> dict[str, Any]:
        return {"ok": False, "executions": [], "error": self.reason, "live_orders": False}

    def reconcile_position(self, symbol: str) -> dict[str, Any]:
        return {"ok": False, "symbol": symbol, "error": self.reason, "live_orders": False, "exchange_order_sent": False}

    def status(self) -> dict[str, Any]:
        return {
            "adapter": "DeniedLiveExecutionAdapter",
            "live_mutate_allowed": live_mutate_allowed(),
            "bybit_is_mainnet": bybit_is_mainnet(),
            "live_session_token_present": live_session_token_present(),
            "private_order_http_implemented": False,
            "live_orders": False,
            "execution_allowed": False,
            "exchange_order_sent": False,
            "reason": self.reason,
        }


@dataclass
class LiveBybitExecutionAdapter:
    """Real Bybit V5 MAINNET order adapter (pybit write session)."""

    seen_intents: set[str] = field(default_factory=set)
    _session: Any | None = None

    def _http(self) -> Any:
        if not live_mutate_allowed():
            raise LiveExecutionDisabled("live_authorization_incomplete")
        if not bybit_is_mainnet():
            raise LiveExecutionDisabled("bybit_not_mainnet")
        if self._session is None:
            from bot.client import create_write_session

            self._session = create_write_session()
        return self._session

    def _ret(self, raw: dict[str, Any]) -> dict[str, Any]:
        if int(raw.get("retCode", -1)) != 0:
            raise LiveExecutionDisabled(f"bybit_error:{raw.get('retCode')}:{raw.get('retMsg')}")
        result = raw.get("result")
        return result if isinstance(result, dict) else {}

    def fetch_balance(self) -> dict[str, Any]:
        raw = self._http().get_wallet_balance(accountType="UNIFIED")
        result = self._ret(raw)
        return {"ok": True, "result": result, "live_orders": True, "execution_allowed": True}

    def fetch_instrument(self, symbol: str) -> dict[str, Any]:
        raw = self._http().get_instruments_info(category="linear", symbol=symbol.upper())
        result = self._ret(raw)
        rows = result.get("list") or []
        return {"ok": True, "symbol": symbol.upper(), "instrument": rows[0] if rows else None, "live_orders": True}

    def fetch_positions(self, symbol: str) -> dict[str, Any]:
        raw = self._http().get_positions(category="linear", symbol=symbol.upper())
        result = self._ret(raw)
        return {"ok": True, "symbol": symbol.upper(), "positions": result.get("list") or [], "live_orders": True}

    def set_leverage(self, *, symbol: str, leverage: int | str, category: str = "linear") -> dict[str, Any]:
        lev = str(int(leverage))
        try:
            raw = self._http().set_leverage(
                category=category or "linear",
                symbol=str(symbol).upper(),
                buyLeverage=lev,
                sellLeverage=lev,
            )
        except Exception as exc:  # noqa: BLE001
            # 110043 = leverage not modified (already set) — treat as ok when message says so.
            text = str(exc)
            if "110043" in text:
                return {"ok": True, "leverage": lev, "unchanged": True, "live_orders": True}
            raise LiveExecutionDisabled(f"bybit_set_leverage:{exc}") from exc
        code = int(raw.get("retCode", -1))
        if code in {0, 110043}:
            return {"ok": True, "leverage": lev, "unchanged": code == 110043, "raw": raw, "live_orders": True}
        raise LiveExecutionDisabled(f"bybit_error:{code}:{raw.get('retMsg')}")

    def place_order(self, **kwargs: Any) -> dict[str, Any]:
        intent = str(kwargs.get("intent_key") or kwargs.get("orderLinkId") or "")
        if intent:
            if intent in self.seen_intents:
                raise LiveExecutionDisabled("duplicate_live_intent_refused")
            self.seen_intents.add(intent)
        link = str(
            kwargs.get("orderLinkId")
            or durable_client_order_id(
                symbol=str(kwargs.get("symbol") or ""),
                side=str(kwargs.get("side") or ""),
                intent_key=intent or f"{time.time_ns()}",
            )
        )[:36]
        order_type = str(kwargs.get("orderType") or kwargs.get("order_type") or "Market")
        # Bybit rejects Market + GTC (InvalidRequestError). Use IOC for market.
        default_tif = "IOC" if order_type.lower() == "market" else "GTC"
        payload: dict[str, Any] = {
            "category": kwargs.get("category") or "linear",
            "symbol": str(kwargs.get("symbol") or "").upper(),
            "side": kwargs.get("side"),
            "orderType": order_type,
            "qty": str(kwargs.get("qty")),
            "orderLinkId": link,
            "timeInForce": kwargs.get("timeInForce") or default_tif,
            "positionIdx": int(kwargs.get("positionIdx") or 0),
        }
        if kwargs.get("price") is not None:
            payload["price"] = str(kwargs["price"])
        if kwargs.get("stopLoss") is not None:
            payload["stopLoss"] = str(kwargs["stopLoss"])
        if kwargs.get("takeProfit") is not None:
            payload["takeProfit"] = str(kwargs["takeProfit"])
        if kwargs.get("reduceOnly") is not None or kwargs.get("reduce_only") is not None:
            payload["reduceOnly"] = bool(kwargs.get("reduceOnly", kwargs.get("reduce_only")))
        try:
            raw = self._http().place_order(**payload)
        except Exception as exc:  # noqa: BLE001 — surface Bybit/pybit reason
            raise LiveExecutionDisabled(f"bybit_place_order:{exc}") from exc
        result = self._ret(raw)
        return {
            "ok": True,
            "client_order_id": link,
            "exchange_order_id": result.get("orderId"),
            "result": result,
            "raw": raw,
            "live_orders": True,
            "execution_allowed": True,
            "exchange_order_sent": True,
            "acknowledged_at_ms": int(time.time() * 1000),
        }

    def cancel_order(self, **kwargs: Any) -> dict[str, Any]:
        payload = {
            "category": kwargs.get("category") or "linear",
            "symbol": str(kwargs.get("symbol") or "").upper(),
        }
        if kwargs.get("orderId"):
            payload["orderId"] = kwargs["orderId"]
        if kwargs.get("orderLinkId"):
            payload["orderLinkId"] = kwargs["orderLinkId"]
        try:
            raw = self._http().cancel_order(**payload)
        except Exception as exc:  # noqa: BLE001
            raise LiveExecutionDisabled(f"bybit_cancel_order:{exc}") from exc
        result = self._ret(raw)
        return {"ok": True, "result": result, "raw": raw, "live_orders": True, "exchange_order_sent": True}

    def get_order_status(self, **kwargs: Any) -> dict[str, Any]:
        # openOnly=0 → truly open orders only (not recent history).
        call_kwargs: dict[str, Any] = {
            "category": kwargs.get("category") or "linear",
            "symbol": str(kwargs.get("symbol") or "").upper(),
            "openOnly": 0,
            "limit": 50,
        }
        if kwargs.get("orderLinkId"):
            call_kwargs["orderLinkId"] = kwargs["orderLinkId"]
        if kwargs.get("orderId"):
            call_kwargs["orderId"] = kwargs["orderId"]
        raw = self._http().get_open_orders(**call_kwargs)
        result = self._ret(raw)
        rows = [row for row in (result.get("list") or []) if isinstance(row, dict)]
        return {
            "ok": True,
            "order": rows[0] if rows else None,
            "orders": rows,
            "live_orders": True,
        }

    def place_protective_orders(self, **kwargs: Any) -> dict[str, Any]:
        raw = self._http().set_trading_stop(
            category=kwargs.get("category") or "linear",
            symbol=str(kwargs.get("symbol") or "").upper(),
            stopLoss=kwargs.get("stopLoss") or kwargs.get("stop_loss"),
            takeProfit=kwargs.get("takeProfit") or kwargs.get("take_profit"),
            positionIdx=int(kwargs.get("positionIdx") or 0),
        )
        result = self._ret(raw)
        return {"ok": True, "result": result, "live_orders": True, "exchange_order_sent": True}

    def fetch_executions(self, **kwargs: Any) -> dict[str, Any]:
        raw = self._http().get_executions(
            category=kwargs.get("category") or "linear",
            symbol=str(kwargs.get("symbol") or "").upper(),
            orderId=kwargs.get("order_id") or kwargs.get("orderId"),
        )
        result = self._ret(raw)
        return {"ok": True, "executions": result.get("list") or [], "live_orders": True}

    def reconcile_position(self, symbol: str) -> dict[str, Any]:
        pos = self.fetch_positions(symbol)
        return {
            **pos,
            "checked_at_ms": int(time.time() * 1000),
            "exchange_order_sent": False,
        }

    def status(self) -> dict[str, Any]:
        return {
            "adapter": "LiveBybitExecutionAdapter",
            "live_mutate_allowed": live_mutate_allowed(),
            "bybit_is_mainnet": bybit_is_mainnet(),
            "live_session_token_present": live_session_token_present(),
            "live_session_token_fingerprint": live_session_token_fingerprint(),
            "private_order_http_implemented": True,
            "live_orders": True,
            "execution_allowed": live_mutate_allowed(),
            "exchange_order_sent": False,
            "reason": "mainnet_live_armed" if live_mutate_allowed() else "gates_incomplete",
        }


# Backward-compatible alias used by older imports/tests.
PreparedLiveExecutionAdapter = LiveBybitExecutionAdapter


def get_default_live_adapter() -> DeniedLiveExecutionAdapter | LiveBybitExecutionAdapter:
    if live_mutate_allowed():
        return LiveBybitExecutionAdapter()
    return DeniedLiveExecutionAdapter()
