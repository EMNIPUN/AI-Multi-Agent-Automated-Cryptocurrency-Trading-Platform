"""Allowlists, redaction, and prompt-injection refusal for the orchestrator."""

from __future__ import annotations

import re
from typing import Any

ALLOWED_TOOLS = frozenset(
    {
        "supervisor_status",
        "analyze_symbol",
        "paper_report",
        "supervisor_command",
        "openai_usage",
        "live_readiness",
        "hype_feasibility",
        "run_full_analysis",
        "agent_status",
        "get_market_price",
        "list_market_quotes",
        "propose_paper_trade",
        "approve_paper_trade",
        "reject_paper_trade",
        "propose_live_trade",
        "approve_live_trade",
        "reject_live_trade",
        "propose_live_close",
        "propose_live_cancel_orders",
        "list_live_positions",
        "start_futures_intake",
        "continue_futures_intake",
    }
)

ALLOWED_COMMANDS = frozenset({"start", "pause", "resume", "stop", "halt"})

FORBIDDEN_ARGUMENT_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "order_link_id",
        "agent_allow_live",
        "leverage",
    }
)

_INJECTION = (
    "ignore previous instructions",
    "ignore all previous",
    "reveal the api key",
    "reveal the secret",
    "agent_allow_live",
    "drop table",
    "system prompt",
    "bypass the risk",
    "override risk",
    "without approval",
    "skip approval",
)

_SECRET = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9._\-]{8,}|://[^:\s]+:[^@\s]+@)",
    re.IGNORECASE,
)


def injection_refusal(message: str) -> str | None:
    text = (message or "").lower()
    for phrase in _INJECTION:
        if phrase in text:
            return "prompt_injection_refused"
    return None


def validate_tool_call(name: str, arguments: dict[str, Any] | None) -> str | None:
    if name not in ALLOWED_TOOLS:
        return "tool_not_allowed"
    args = arguments or {}
    if not isinstance(args, dict):
        return "tool_arguments_invalid"
    forbidden = FORBIDDEN_ARGUMENT_KEYS.intersection(k.lower() for k in args)
    if forbidden:
        return "tool_argument_forbidden"
    if name == "supervisor_command":
        command = str(args.get("command") or "").strip().lower()
        if command not in ALLOWED_COMMANDS:
            return "tool_arguments_invalid"
    if name in {
        "analyze_symbol",
        "run_full_analysis",
        "get_market_price",
        "propose_paper_trade",
        "propose_live_trade",
        "propose_live_close",
        "propose_live_cancel_orders",
        "list_live_positions",
        "start_futures_intake",
    }:
        symbol = str(args.get("symbol") or "")
        if not re.fullmatch(r"[A-Z0-9]{2,20}", symbol):
            return "tool_arguments_invalid"
    if name == "continue_futures_intake":
        # message may be empty; no symbol required
        pass
    if name in {"approve_paper_trade", "reject_paper_trade"}:
        pid = args.get("proposal_id")
        if pid is not None and str(pid).strip() != "":
            if not re.fullmatch(r"ptp_[a-f0-9]{8,32}", str(pid).strip()):
                return "tool_arguments_invalid"
    if name in {"approve_live_trade", "reject_live_trade"}:
        pid = args.get("proposal_id")
        if pid is not None and str(pid).strip() != "":
            if not re.fullmatch(r"ltp_[a-f0-9]{8,32}", str(pid).strip()):
                return "tool_arguments_invalid"
    return None


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return _SECRET.sub("[redacted]", value)
    if isinstance(value, dict):
        return {str(k): redact(v) for k, v in value.items() if str(k).lower() not in {"api_key", "api_secret", "password"}}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
