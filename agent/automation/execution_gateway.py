"""Execution permission gateway — strict PAPER / TESTNET / LIVE separation.

Chat cannot flip modes. LIVE mutate requires operator env gates; each order still
needs explicit Orchestrator chat Approve via live trade proposals.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any  # noqa: F401 — used throughout

from agent.automation.modes import TradingMode, get_automation_gates, parse_trading_mode


def _live_helpers() -> tuple[Any, Any, Any, Any]:
    from apps.api.app.exchange.bybit_live_adapter import (
        DeniedLiveExecutionAdapter,
        get_default_live_adapter,
        live_mutate_allowed,
        live_session_token_present,
    )

    return DeniedLiveExecutionAdapter, get_default_live_adapter, live_mutate_allowed, live_session_token_present


class ExecutionLane(str, Enum):
    PAPER = "PAPER"
    TESTNET = "TESTNET"
    LIVE = "LIVE"
    BLOCKED = "BLOCKED"


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class GatewayDecision:
    lane: ExecutionLane
    allowed: bool
    reason: str
    live_orders: bool
    exchange_order_sent: bool
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane.value,
            "allowed": self.allowed,
            "reason": self.reason,
            "live_orders": self.live_orders,
            "execution_allowed": self.allowed and self.lane is ExecutionLane.PAPER,
            "exchange_order_sent": self.exchange_order_sent,
            "details": self.details,
        }


class ExecutionPermissionGateway:
    """Decides which execution lane may run. Never mints live session tokens."""

    def __init__(self, *, live_adapter: Any | None = None) -> None:
        _, get_default_live_adapter, _, _ = _live_helpers()
        self.live_adapter = live_adapter or get_default_live_adapter()

    def resolve_lane(self, requested_mode: str | None = None) -> GatewayDecision:
        _, _, live_mutate_allowed, live_session_token_present = _live_helpers()
        mode = parse_trading_mode(requested_mode) if requested_mode else parse_trading_mode()
        gates = get_automation_gates()
        allow_live = _flag("AGENT_ALLOW_LIVE")
        requested = str(requested_mode or "").strip().upper()
        details = {
            "CRYPTONOVA_TRADING_MODE": mode.value,
            "AGENT_ALLOW_LIVE": allow_live,
            "MAINNET_TRADING_ENABLED": gates.mainnet_trading_enabled,
            "live_session_token_present": live_session_token_present(),
            "live_mutate_allowed": live_mutate_allowed(),
            "testnet_order_submission_allowed": gates.order_submission_allowed,
            "human_approve_per_order": True,
        }

        if requested in {"LIVE", "MAINNET", "MAINNET_TRADING"} or mode is TradingMode.MAINNET_TRADING:
            if not live_mutate_allowed():
                return GatewayDecision(
                    lane=ExecutionLane.BLOCKED,
                    allowed=False,
                    reason="live_authorization_incomplete",
                    live_orders=False,
                    exchange_order_sent=False,
                    details=details,
                )
            return GatewayDecision(
                lane=ExecutionLane.LIVE,
                allowed=True,
                reason="live_lane_armed_approve_required",
                live_orders=True,
                exchange_order_sent=False,
                details=details,
            )

        if mode is TradingMode.TESTNET_TRADING:
            if not gates.order_submission_allowed:
                return GatewayDecision(
                    lane=ExecutionLane.BLOCKED,
                    allowed=False,
                    reason="testnet_submission_not_approved",
                    live_orders=False,
                    exchange_order_sent=False,
                    details=details,
                )
            # Wired to AutomatedExecutionPipeline / BybitTestnetTradingAdapter.
            # LIVE remains denied. Chat cannot set these gates.
            return GatewayDecision(
                lane=ExecutionLane.TESTNET,
                allowed=True,
                reason="testnet_lane_armed",
                live_orders=False,
                exchange_order_sent=False,
                details={
                    **details,
                    "orchestrator_wired": True,
                    "adapter": "BybitTestnetTradingAdapter",
                },
            )

        if mode in {TradingMode.PAPER_TRADING, TradingMode.SIGNALS_ONLY} or requested_mode in {
            None,
            "",
            "PAPER",
            "paper",
        }:
            return GatewayDecision(
                lane=ExecutionLane.PAPER,
                allowed=True,
                reason="paper_lane",
                live_orders=False,
                exchange_order_sent=False,
                details=details,
            )

        return GatewayDecision(
            lane=ExecutionLane.BLOCKED,
            allowed=False,
            reason="unknown_mode",
            live_orders=False,
            exchange_order_sent=False,
            details=details,
        )

    def submit(
        self,
        *,
        requested_mode: str = "PAPER",
        order: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Attempt submit. PAPER is acknowledged as simulated; LIVE/TESTNET stay denied here."""
        decision = self.resolve_lane(requested_mode)
        body = decision.to_dict()
        body["order"] = order or {}
        if decision.lane is ExecutionLane.PAPER and decision.allowed:
            body["status"] = "PAPER_SIMULATED_ONLY"
            body["summary"] = (
                "Execution gateway selected PAPER.\n"
                "Simulated orders are owned by the paper supervisor/broker.\n"
                "No Bybit live or testnet order was sent."
            )
            return body
        if decision.lane is ExecutionLane.LIVE and decision.allowed:
            try:
                placed = self.live_adapter.place_order(**(order or {}))
                body["status"] = "LIVE_SUBMITTED"
                body["result"] = placed
                body["live_orders"] = True
                body["execution_allowed"] = True
                body["exchange_order_sent"] = bool(placed.get("exchange_order_sent"))
                body["summary"] = (
                    "LIVE lane submitted via Bybit MAINNET adapter.\n"
                    "Prefer Orchestrator propose_live_trade + Approve for chat control."
                )
                return body
            except Exception as exc:  # noqa: BLE001 — map to safe denial
                body["status"] = "LIVE_DENIED"
                body["error"] = type(exc).__name__
                body["summary"] = (
                    "LIVE lane refused by adapter.\n"
                    f"Reason: {getattr(exc, 'reason', str(exc))}."
                )
                body["live_orders"] = True
                body["exchange_order_sent"] = False
                return body
        body["status"] = "BLOCKED"
        body["summary"] = (
            f"Execution gateway blocked lane={decision.lane.value}.\n"
            f"Reason: {decision.reason}.\n"
            "No exchange order was sent."
        )
        return body

    def status(self) -> dict[str, Any]:
        _, _, live_mutate_allowed, _ = _live_helpers()
        paper = self.resolve_lane("PAPER").to_dict()
        live = self.resolve_lane("LIVE").to_dict()
        adapter = self.live_adapter.status() if hasattr(self.live_adapter, "status") else {}
        armed = live_mutate_allowed()
        return {
            "paper": paper,
            "live": live,
            "live_adapter": adapter,
            "live_orders": armed,
            "execution_allowed": armed,
            "exchange_order_sent": False,
            "human_approve_per_order": True,
            "summary": (
                "Execution gateway: PAPER simulated; "
                + (
                    "LIVE MAINNET armed — each Orchestrator order needs chat Approve."
                    if armed
                    else "LIVE not armed (set AGENT_ALLOW_LIVE + MAINNET_TRADING_ENABLED)."
                )
            ),
        }
