"""Typed, mode-scoped tool registry for Orchestrator V2.

OpenAI only receives schemas permitted for the active mode and live arming state.
Server-side validate_tool_call remains the hard execution gate.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from agent.orchestrator.guard import ALLOWED_TOOLS


class ToolClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    PAPER_CONTROL = "PAPER_CONTROL"
    LIVE_MUTATION = "LIVE_MUTATION"
    LIVE_READ = "LIVE_READ"


TOOL_CLASS: dict[str, ToolClass] = {
    "supervisor_status": ToolClass.READ_ONLY,
    "paper_report": ToolClass.READ_ONLY,
    "analyze_symbol": ToolClass.READ_ONLY,
    "run_full_analysis": ToolClass.READ_ONLY,
    "agent_status": ToolClass.READ_ONLY,
    "get_market_price": ToolClass.READ_ONLY,
    "list_market_quotes": ToolClass.READ_ONLY,
    "openai_usage": ToolClass.READ_ONLY,
    "live_readiness": ToolClass.READ_ONLY,
    "hype_feasibility": ToolClass.READ_ONLY,
    "supervisor_command": ToolClass.PAPER_CONTROL,
    "propose_paper_trade": ToolClass.PAPER_CONTROL,
    "approve_paper_trade": ToolClass.PAPER_CONTROL,
    "reject_paper_trade": ToolClass.PAPER_CONTROL,
    "list_live_positions": ToolClass.LIVE_READ,
    "propose_live_trade": ToolClass.LIVE_MUTATION,
    "approve_live_trade": ToolClass.LIVE_MUTATION,
    "reject_live_trade": ToolClass.LIVE_MUTATION,
    "propose_live_close": ToolClass.LIVE_MUTATION,
    "propose_live_cancel_orders": ToolClass.LIVE_MUTATION,
    "start_futures_intake": ToolClass.LIVE_MUTATION,
    "continue_futures_intake": ToolClass.LIVE_MUTATION,
}

LIVE_MUTATION_TOOLS = frozenset(
    name for name, cls in TOOL_CLASS.items() if cls == ToolClass.LIVE_MUTATION
)
LIVE_READ_TOOLS = frozenset(
    name for name, cls in TOOL_CLASS.items() if cls == ToolClass.LIVE_READ
)
PAPER_CONTROL_TOOLS = frozenset(
    name for name, cls in TOOL_CLASS.items() if cls == ToolClass.PAPER_CONTROL
)
READ_ONLY_TOOLS = frozenset(
    name for name, cls in TOOL_CLASS.items() if cls == ToolClass.READ_ONLY
)


def classify(name: str) -> ToolClass | None:
    return TOOL_CLASS.get(str(name or ""))


def allowed_tool_names(*, preferred_mode: str = "PAPER", live_armed: bool = False) -> frozenset[str]:
    """Names the model may request for this chat mode."""
    mode = "LIVE" if str(preferred_mode or "").strip().upper() == "LIVE" else "PAPER"
    names = set(READ_ONLY_TOOLS) | set(PAPER_CONTROL_TOOLS)
    if mode == "LIVE" and live_armed:
        names |= set(LIVE_READ_TOOLS) | set(LIVE_MUTATION_TOOLS)
    elif mode == "LIVE":
        # LIVE chat without env arming: readiness + positions read only if listed.
        names |= {"live_readiness"}
    return frozenset(n for n in names if n in ALLOWED_TOOLS)


def schemas_for(
    all_schemas: list[dict[str, Any]],
    *,
    preferred_mode: str = "PAPER",
    live_armed: bool = False,
) -> list[dict[str, Any]]:
    allowed = allowed_tool_names(preferred_mode=preferred_mode, live_armed=live_armed)
    out: list[dict[str, Any]] = []
    for schema in all_schemas:
        name = str(schema.get("name") or "")
        if name in allowed:
            out.append(schema)
    return out


def is_side_effecting(name: str) -> bool:
    cls = classify(name)
    return cls in {ToolClass.PAPER_CONTROL, ToolClass.LIVE_MUTATION}


def permission_matrix() -> dict[str, Any]:
    return {
        "READ_ONLY": sorted(READ_ONLY_TOOLS),
        "PAPER_CONTROL": sorted(PAPER_CONTROL_TOOLS),
        "LIVE_READ": sorted(LIVE_READ_TOOLS),
        "LIVE_MUTATION": sorted(LIVE_MUTATION_TOOLS),
        "paper_mode_openai": sorted(allowed_tool_names(preferred_mode="PAPER", live_armed=False)),
        "live_armed_openai": sorted(allowed_tool_names(preferred_mode="LIVE", live_armed=True)),
    }
