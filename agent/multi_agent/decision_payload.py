"""Versioned serialization of CoordinatorDecision for local outbox / cloud sync."""

from __future__ import annotations

from typing import Any

from agent.multi_agent.types import CoordinatorDecision
from apps.api.app.sanitize import sanitize_public_json

PAYLOAD_SCHEMA_VERSION = "4D.1.0"


def build_decision_sync_payload(decision: CoordinatorDecision) -> dict[str, Any]:
    """
    Full public decision envelope for durable outbox.

    Never includes secrets. Does not fabricate missing indicators.
    """
    public = sanitize_public_json(decision.to_public_dict())
    indicators: dict[str, Any] = {}
    for c in public.get("contributions") or []:
        if isinstance(c, dict) and c.get("indicators"):
            indicators[str(c.get("agent_id"))] = c["indicators"]
    return {
        "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
        "decision": public,
        "indicators_by_agent": indicators,
        "legacy": False,
        "not_an_order": True,
        "execution_allowed": False,
    }


def validate_decision_sync_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "payload_not_object"
    ver = str(payload.get("payload_schema_version") or "")
    if not ver:
        return False, "missing_schema_version"
    decision = payload.get("decision")
    if not isinstance(decision, dict):
        return False, "missing_decision"
    for key in (
        "decision_id",
        "idempotent_key",
        "symbol",
        "category",
        "interval",
        "action",
        "timestamp_ms",
        "strategy_version",
    ):
        if key not in decision:
            return False, f"missing_decision_field:{key}"
    if decision.get("execution_allowed") is True:
        return False, "execution_allowed_must_be_false"
    return True, "ok"


def is_legacy_summary_payload(payload: dict[str, Any]) -> bool:
    """Pre-4D.1.0 outbox rows that only stored summary fields."""
    if payload.get("payload_schema_version"):
        return False
    return "decision" not in payload and "decision_id" in payload
