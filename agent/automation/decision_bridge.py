"""Bridge CoordinatorDecision → ExecutionPermissionGateway → PAPER/TESTNET lanes.

LIVE remains denied. LLM/news cannot open this bridge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.automation.execution_gateway import (
    ExecutionLane,
    ExecutionPermissionGateway,
    GatewayDecision,
)
from agent.automation.pipeline import (
    AutomatedExecutionPipeline,
    PipelineResult,
    SignalExecutionRequest,
)
from agent.multi_agent.types import CoordinatorDecision, DecisionAction


@dataclass(frozen=True)
class BridgeResult:
    gateway: dict[str, Any]
    executed: bool
    lane: str
    paper: dict[str, Any] | None = None
    testnet: dict[str, Any] | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "gateway": self.gateway,
            "executed": self.executed,
            "lane": self.lane,
            "paper": self.paper,
            "testnet": self.testnet,
            "detail": self.detail,
            "live_orders": False,
            "exchange_order_sent": bool(
                self.testnet and self.testnet.get("submitted") and self.testnet.get("exchange_order_id")
            ),
            "execution_allowed": self.executed and self.lane == ExecutionLane.PAPER.value,
        }


def decision_to_execution_request(
    decision: CoordinatorDecision | dict[str, Any],
    *,
    intended_notional: float = 100.0,
    data_age_ms: int = 0,
    spread_bps: float = 0.0,
) -> SignalExecutionRequest | None:
    """Map an actionable decision + levels to a SignalExecutionRequest.

    HOLD/BLOCKED return None. Does not flip execution_allowed on the decision.
    """
    if isinstance(decision, CoordinatorDecision):
        action = decision.action
        public = decision.to_public_dict()
    else:
        public = decision
        action_raw = str(public.get("action") or "").upper()
        try:
            action = DecisionAction(action_raw)
        except ValueError:
            return None

    if action not in {DecisionAction.BUY, DecisionAction.SELL}:
        return None

    levels = public.get("levels") if isinstance(public.get("levels"), dict) else {}
    entry = levels.get("entry")
    if entry is None:
        market = public.get("market") if isinstance(public.get("market"), dict) else {}
        entry = market.get("last_price")
    if entry is None:
        return None

    side = "Buy" if action is DecisionAction.BUY else "Sell"
    return SignalExecutionRequest(
        decision_id=str(public.get("decision_id") or ""),
        symbol=str(public.get("symbol") or "").upper(),
        category=str(public.get("category") or "linear"),
        side=side,
        entry_price=float(entry),
        stop_loss=float(levels["stop_loss"]) if levels.get("stop_loss") is not None else None,
        take_profit=float(levels["take_profit"]) if levels.get("take_profit") is not None else None,
        strategy_version=str(public.get("strategy_version") or ""),
        correlation_id=str(public.get("correlation_id") or ""),
        data_age_ms=data_age_ms,
        spread_bps=spread_bps,
        intended_notional=float(intended_notional),
    )


def route_decision(
    decision: CoordinatorDecision | dict[str, Any],
    *,
    gateway: ExecutionPermissionGateway | None = None,
    paper_executor: Any | None = None,
    testnet_pipeline: AutomatedExecutionPipeline | None = None,
    requested_mode: str | None = None,
    intended_notional: float = 100.0,
) -> BridgeResult:
    """Resolve gateway lane and optionally execute PAPER or gated TESTNET."""
    gw = gateway or ExecutionPermissionGateway()
    gate = gw.resolve_lane(requested_mode)
    gate_dict = gate.to_dict()

    if not gate.allowed and gate.lane is not ExecutionLane.PAPER:
        # PAPER may still be allowed via separate allowed flag.
        pass

    req = decision_to_execution_request(decision, intended_notional=intended_notional)
    if req is None:
        return BridgeResult(
            gateway=gate_dict,
            executed=False,
            lane=gate.lane.value,
            detail="decision_not_actionable",
        )

    if gate.lane is ExecutionLane.PAPER and gate.allowed:
        paper_result: dict[str, Any] | None = None
        if paper_executor is not None and hasattr(paper_executor, "apply_decision"):
            # Caller supplies AutomaticPaperTrader-compatible object + candle externally.
            paper_result = {"deferred": True, "reason": "paper_executor_requires_candle_context"}
        return BridgeResult(
            gateway=gate_dict,
            executed=False,
            lane=ExecutionLane.PAPER.value,
            paper=paper_result or {"ready": True, "request": {
                "decision_id": req.decision_id,
                "symbol": req.symbol,
                "side": req.side,
                "entry_price": req.entry_price,
                "stop_loss": req.stop_loss,
                "take_profit": req.take_profit,
            }},
            detail="paper_lane_mapped",
        )

    if gate.lane is ExecutionLane.TESTNET and gate.allowed:
        pipeline = testnet_pipeline or AutomatedExecutionPipeline()
        result: PipelineResult = pipeline.process(req)
        return BridgeResult(
            gateway=gate_dict,
            executed=bool(result.submitted),
            lane=ExecutionLane.TESTNET.value,
            testnet={
                "mode": result.mode,
                "submitted": result.submitted,
                "state": result.state,
                "intent_id": result.intent_id,
                "client_order_id": result.client_order_id,
                "exchange_order_id": result.exchange_order_id,
                "filled": result.filled,
                "protection_state": result.protection_state,
                "risk": result.risk,
                "detail": result.detail,
            },
            detail=result.detail,
        )

    if gate.lane is ExecutionLane.LIVE:
        return BridgeResult(
            gateway=gate_dict,
            executed=False,
            lane=ExecutionLane.LIVE.value,
            detail="live_denied",
        )

    return BridgeResult(
        gateway=gate_dict,
        executed=False,
        lane=gate.lane.value,
        detail=gate.reason,
    )


def authorize_testnet_gateway(gate: GatewayDecision) -> GatewayDecision:
    """Helper used by tests when dual submission gates are open."""
    return gate
