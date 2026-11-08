"""Compare an LLM suggestion with the deterministic decision. Never mutates it."""

from __future__ import annotations


def agreement_status(
    *,
    coordinator_action: str,
    suggested_action: str | None,
    abstain: bool,
    valid: bool,
) -> str:
    if not valid or not suggested_action:
        return "not_applicable"
    if abstain or suggested_action == "ABSTAIN":
        return "abstain"
    if coordinator_action == suggested_action:
        return "agree"
    return "disagree"


def influence_flags() -> dict[str, bool]:
    return {
        "llm_changed_decision": False,
        "execution_allowed": False,
        "places_orders": False,
    }
