"""Phase 6A automation foundation — Testnet-first, default SIGNALS_ONLY."""

from agent.automation.modes import TradingMode, get_automation_gates, gates_public_dict
from agent.automation.pipeline import AutomatedExecutionPipeline, status_bundle

__all__ = [
    "AutomatedExecutionPipeline",
    "TradingMode",
    "get_automation_gates",
    "gates_public_dict",
    "status_bundle",
]
