"""Phase 4B — signals-only multi-agent intelligence + local history."""

from agent.multi_agent.config import STRATEGY_VERSION
from agent.multi_agent.pipeline import SignalPipeline, evaluate_signals
from agent.multi_agent.types import CoordinatorDecision, DecisionAction

__all__ = [
    "STRATEGY_VERSION",
    "CoordinatorDecision",
    "DecisionAction",
    "SignalPipeline",
    "evaluate_signals",
]
