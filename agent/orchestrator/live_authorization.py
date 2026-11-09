"""Live activation readiness checklist and bypass-approval refusal.

MAINNET live orders are allowed only when operator env gates are armed and
each order receives an explicit chat Approve. Chat cannot mint tokens or flip env.
"""

from __future__ import annotations

import os
from typing import Any


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def live_activation_request_template() -> dict[str, Any]:
    return {
        "exchange": "Bybit",
        "exchange_account_identity": "operator_mainnet_account",
        "symbol": "HYPEUSDT",
        "market": "linear_usdt_perpetual",
        "execution_mode": "LIVE",
        "strategy_version": "orchestrator_chat_approve",
        "capital_budget_usdt": "25",
        "max_risk_per_trade": "0.01",
        "max_daily_loss": "operator_defined",
        "max_drawdown": "operator_defined",
        "max_exposure": "25",
        "max_leverage": "1",
        "max_concurrent_positions": 1,
        "session_duration_hours": 48,
        "stop_loss_required": True,
        "human_approve_per_order": True,
        "emergency_stop_procedure": (
            "1) Orchestrator chat: Emergency halt\n"
            "2) Clear CRYPTONOVA_LIVE_SESSION_TOKEN if set\n"
            "3) Set AGENT_ALLOW_LIVE=false and MAINNET_TRADING_ENABLED=false\n"
            "4) Verify exchange positions and cancel unprotected live orders manually if needed"
        ),
        "revocable": True,
        "auto_renew": False,
        "operator_approval_required": True,
        "approved": False,
        "chat_cannot_mint_token": True,
        "note": (
            "Arm AGENT_ALLOW_LIVE + MAINNET_TRADING_ENABLED on Bybit mainnet. "
            "Every live order still needs explicit chat Approve."
        ),
    }


def live_readiness_checklist(
    *,
    paper_supervisor_enabled: bool = False,
    openai_spend_approved: bool = False,
) -> dict[str, Any]:
    from apps.api.app.exchange.bybit_live_adapter import (
        bybit_is_mainnet,
        live_mutate_allowed,
        live_session_token_present,
    )

    token_present = live_session_token_present()
    armed = live_mutate_allowed()
    mainnet = bybit_is_mainnet()
    gates = {
        "A_autonomous_paper": {
            "label": "Autonomous paper validation",
            "status": "READY" if paper_supervisor_enabled or _flag("CRYPTONOVA_PAPER_SUPERVISOR") else "OPTIONAL",
            "evidence": "Paper supervisor remains available for simulated runs.",
            "complete": True,
        },
        "B_bybit_mainnet": {
            "label": "Bybit MAINNET private order path",
            "status": "ARMED" if armed else "NOT_ARMED",
            "evidence": (
                "LiveBybitExecutionAdapter places orders only after chat Approve "
                "when AGENT_ALLOW_LIVE and MAINNET_TRADING_ENABLED are set on mainnet."
            ),
            "complete": armed,
        },
        "C_human_approve": {
            "label": "Per-order chat Approve",
            "status": "REQUIRED",
            "evidence": "propose_live_trade → Approve live trade. No silent auto-submit.",
            "complete": True,
        },
        "D_operational_reliability": {
            "label": "Operational reliability",
            "status": "OPERATOR_OWNED",
            "evidence": "Emergency halt + env revoke remain the kill switch.",
            "complete": True,
        },
    }
    flags = {
        "AGENT_ALLOW_LIVE": _flag("AGENT_ALLOW_LIVE"),
        "MAINNET_TRADING_ENABLED": _flag("MAINNET_TRADING_ENABLED"),
        "BYBIT_MAINNET": mainnet,
        "ORCHESTRATOR_OPENAI_ENABLED": _flag("ORCHESTRATOR_OPENAI_ENABLED"),
        "ORCHESTRATOR_OPENAI_SPEND_APPROVED": openai_spend_approved
        or _flag("ORCHESTRATOR_OPENAI_SPEND_APPROVED"),
        "CRYPTONOVA_PAPER_SUPERVISOR": paper_supervisor_enabled
        or _flag("CRYPTONOVA_PAPER_SUPERVISOR"),
        "CRYPTONOVA_LIVE_SESSION_TOKEN_PRESENT": token_present,
        "live_mutate_allowed": armed,
    }
    if armed:
        summary_lines = [
            "LIVE readiness — MAINNET armed for Orchestrator chat Approve workflow.",
            "Propose a live trade, then reply Approve live trade for each order.",
            "Revoke by clearing AGENT_ALLOW_LIVE / MAINNET_TRADING_ENABLED.",
        ]
        verdict = "LIVE_ARMED_APPROVE_REQUIRED"
    else:
        summary_lines = [
            "LIVE readiness — not armed.",
            "Set AGENT_ALLOW_LIVE=true, MAINNET_TRADING_ENABLED=true, BYBIT_TESTNET=false.",
            "Then use propose_live_trade + Approve live trade in Orchestrator chat.",
        ]
        verdict = "LIVE_NOT_ARMED"
    return {
        "verdict": verdict,
        "live_ready": armed,
        "execution_mode": "LIVE" if armed else "PAPER",
        "live_orders": armed,
        "execution_allowed": False,  # still needs per-trade Approve
        "exchange_order_sent": False,
        "human_approve_per_order": True,
        "gates": gates,
        "flags": flags,
        "activation_request_template": live_activation_request_template(),
        "openai_spend_approved": flags["ORCHESTRATOR_OPENAI_SPEND_APPROVED"],
        "revocation": {
            "clear_env": [
                "CRYPTONOVA_LIVE_SESSION_TOKEN",
                "AGENT_ALLOW_LIVE=false",
                "MAINNET_TRADING_ENABLED=false",
            ],
            "auto_renew": False,
        },
        "summary": "\n".join(summary_lines),
    }


def refuse_live_escalation(message: str) -> dict[str, Any] | None:
    """Refuse only bypass-approval / env-mutation attempts — not normal live propose/approve chat."""
    text = (message or "").lower()
    bypass = (
        "without approval",
        "skip approval",
        "no approval needed",
        "auto approve live",
        "auto-approve live",
        "enable agent_allow_live",
        "set agent_allow_live",
        "set mainnet_trading_enabled",
        "mint live session",
        "unlock live without",
    )
    if not any(item in text for item in bypass):
        return None
    body = live_readiness_checklist()
    body["error"] = "live_escalation_refused"
    body["summary"] = (
        "Refused: live env flags and silent auto-submit cannot be changed from chat.\n"
        "Use propose_live_trade, then Approve live trade for each MAINNET order.\n"
        + body["summary"]
    )
    return body
