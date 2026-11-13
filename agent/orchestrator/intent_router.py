"""Hybrid intent router: deterministic LocalPlanner vs OpenAI synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent.orchestrator.service import LocalPlanner, PlannedCall, is_greeting


RouteKind = Literal["greeting", "deterministic", "openai_synthesis", "status_fallback"]


@dataclass(frozen=True)
class RouteDecision:
    kind: RouteKind
    planned: list[PlannedCall] | None = None
    reason: str = ""


def route_intent(message: str, *, preferred_mode: str = "PAPER") -> RouteDecision:
    """Decide whether to answer deterministically or via OpenAI synthesis."""
    mode = "LIVE" if str(preferred_mode or "").strip().upper() == "LIVE" else "PAPER"
    if is_greeting(message):
        return RouteDecision(kind="greeting", reason="short_greeting")
    planned = LocalPlanner().route(message, preferred_mode=mode)
    if planned is not None:
        return RouteDecision(kind="deterministic", planned=planned, reason=planned[0].name)
    text = (message or "").lower()
    synthesis_cues = (
        "why",
        "explain",
        "compare",
        "summarize",
        "summary",
        "what happened",
        "difference",
        "versus",
        "vs ",
        "help me understand",
    )
    if any(cue in text for cue in synthesis_cues):
        return RouteDecision(kind="openai_synthesis", reason="synthesis_request")
    # Ambiguous → OpenAI if gates open (caller decides), else status fallback.
    return RouteDecision(kind="openai_synthesis", reason="ambiguous")
