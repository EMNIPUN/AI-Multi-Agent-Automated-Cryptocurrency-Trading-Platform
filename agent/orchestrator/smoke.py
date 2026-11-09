"""Controlled OpenAI orchestrator smoke test.

Paid calls require an explicit operator spending approval argument in addition
to ORCHESTRATOR_OPENAI_ENABLED and ORCHESTRATOR_OPENAI_SPEND_APPROVED.
This module never places orders and never changes risk settings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.orchestrator.openai_adapter import (
    FakeResponsesTransport,
    OpenAiOrchestratorPlanner,
    OrchestratorOpenAiConfig,
    TOOL_SCHEMAS,
)
from agent.orchestrator.service import PlannedCall
from agent.orchestrator.usage_ledger import UsageLedger


APPROVAL_PHRASE = "I_APPROVE_ORCHESTRATOR_OPENAI_SPEND"
SMOKE_CEILING_USD = 0.25
READ_ONLY_SMOKE_PROMPT = (
    "Analyze CryptoNova's agent architecture and explain how deterministic "
    "risk controls prevent unsafe trading. Keep the answer concise. "
    "Do not suggest live orders or changing risk limits."
)


def _load_repo_dotenv() -> None:
    """Load gitignored .env for CLI runs without exporting secrets into the shell."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env", override=False)


@dataclass(frozen=True)
class SmokeResult:
    ok: bool
    paid_call_attempted: bool
    openai_called: bool
    live_orders: bool
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "paid_call_attempted": self.paid_call_attempted,
            "openai_called": self.openai_called,
            "live_orders": False,
            "execution_allowed": False,
            "message": self.message,
            "details": self.details,
        }


def operator_approval_checkpoint(config: OrchestratorOpenAiConfig | None = None) -> dict[str, Any]:
    _load_repo_dotenv()
    cfg = config or OrchestratorOpenAiConfig.from_env()
    status = cfg.public_status(UsageLedger(cfg.ledger_path))
    return {
        "checkpoint": "openai_spend_approval_required",
        "approval_phrase": APPROVAL_PHRASE,
        "gates": {
            "ORCHESTRATOR_OPENAI_ENABLED": cfg.enabled,
            "ORCHESTRATOR_OPENAI_SPEND_APPROVED": cfg.spend_approved,
            "api_key_configured": bool(cfg.api_key),
            "model_configured": bool(cfg.model),
            "gates_open": cfg.gates_open(),
        },
        "budget": {
            "daily_budget_usd": cfg.daily_budget_usd,
            "monthly_budget_usd": cfg.monthly_budget_usd,
            "spent_usd_24h": status.get("spent_usd_24h"),
            "spent_usd_30d": status.get("spent_usd_30d"),
            "smoke_ceiling_usd": SMOKE_CEILING_USD,
        },
        "tool_schemas_count": len(TOOL_SCHEMAS),
        "read_only_prompt": READ_ONLY_SMOKE_PROMPT,
        "trading_tools_in_smoke": False,
        "live_orders": False,
        "instructions": (
            "Set both spend gates true, configure key+model, then re-run with "
            f"--approve {APPROVAL_PHRASE}. This prompt alone is not approval."
        ),
        "api_key_redacted": True,
    }


def run_schema_validation_smoke() -> SmokeResult:
    """Offline validation of tool schemas and LocalPlanner fallback. No network."""
    transport = FakeResponsesTransport(
        [
            PlannedCall("openai_usage", {}),
            PlannedCall("place_live_order", {"leverage": "10"}),
        ]
    )
    config = OrchestratorOpenAiConfig(
        enabled=True,
        spend_approved=True,
        api_key="sk-test-not-real",
        model="gpt-test",
        ledger_path="data/orchestrator_usage/smoke_schema.sqlite3",
    )
    planner = OpenAiOrchestratorPlanner(config, transport=transport)
    planned = planner.plan("Show OpenAI API usage.")
    names = [call.name for call in planned]
    ok = names == ["openai_usage"] and planner.last_openai_called is True
    return SmokeResult(
        ok=ok,
        paid_call_attempted=False,
        openai_called=False,
        live_orders=False,
        message="Schema validation smoke completed with fake transport.",
        details={
            "planned_tools": names,
            "disallowed_tool_rejected": "place_live_order" not in names,
            "transport_calls": len(transport.calls),
            "checkpoint": operator_approval_checkpoint(config),
        },
    )


def run_paid_smoke(*, approval_phrase: str, force: bool = False) -> SmokeResult:
    """One bounded read-only paid Responses call. Requires explicit approval phrase."""
    _load_repo_dotenv()
    config = OrchestratorOpenAiConfig.from_env()
    checkpoint = operator_approval_checkpoint(config)
    if approval_phrase != APPROVAL_PHRASE:
        return SmokeResult(
            ok=False,
            paid_call_attempted=False,
            openai_called=False,
            live_orders=False,
            message="Operator spend approval phrase missing or incorrect. No paid call made.",
            details={"checkpoint": checkpoint},
        )
    if not config.gates_open() and not force:
        return SmokeResult(
            ok=False,
            paid_call_attempted=False,
            openai_called=False,
            live_orders=False,
            message="Spend gates are closed. No paid call made.",
            details={"checkpoint": checkpoint},
        )
    # Even with approval, refuse if gates are closed unless force is used in controlled ops.
    if not config.gates_open():
        return SmokeResult(
            ok=False,
            paid_call_attempted=False,
            openai_called=False,
            live_orders=False,
            message="Cannot place paid call while gates are closed.",
            details={"checkpoint": checkpoint},
        )

    ledger = UsageLedger(config.ledger_path)
    before = ledger.summary()
    spent_24h = float(before.get("spent_usd_24h") or 0.0)
    spent_30d = float(before.get("spent_usd_30d") or 0.0)
    if spent_24h >= config.daily_budget_usd:
        return SmokeResult(
            ok=False,
            paid_call_attempted=False,
            openai_called=False,
            live_orders=False,
            message="Daily orchestrator budget already exhausted. No paid call made.",
            details={"checkpoint": checkpoint},
        )
    if spent_30d >= config.monthly_budget_usd:
        return SmokeResult(
            ok=False,
            paid_call_attempted=False,
            openai_called=False,
            live_orders=False,
            message="Monthly orchestrator budget already exhausted. No paid call made.",
            details={"checkpoint": checkpoint},
        )
    remaining_daily = max(0.0, config.daily_budget_usd - spent_24h)
    remaining_monthly = max(0.0, config.monthly_budget_usd - spent_30d)
    if min(remaining_daily, remaining_monthly, SMOKE_CEILING_USD) <= 0.0:
        return SmokeResult(
            ok=False,
            paid_call_attempted=False,
            openai_called=False,
            live_orders=False,
            message="Smoke ceiling or remaining budget is zero. No paid call made.",
            details={"checkpoint": checkpoint, "smoke_ceiling_usd": SMOKE_CEILING_USD},
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        return SmokeResult(
            ok=False,
            paid_call_attempted=False,
            openai_called=False,
            live_orders=False,
            message=f"OpenAI SDK unavailable: {exc}",
            details={"checkpoint": checkpoint},
        )

    client = OpenAI(api_key=config.api_key, timeout=config.timeout_seconds)
    try:
        response = client.responses.create(
            model=config.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are CryptoNova's Orchestrator. PAPER mode only. "
                        "Explain architecture and risk gates. Do not suggest live orders, "
                        "do not invent market prices, and do not change permissions."
                    ),
                },
                {
                    "role": "user",
                    "content": checkpoint["read_only_prompt"],
                },
            ],
            # No tools — read-only architecture smoke.
            timeout=config.timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 — map without leaking secrets
        return SmokeResult(
            ok=False,
            paid_call_attempted=True,
            openai_called=False,
            live_orders=False,
            message=f"Paid smoke failed: {type(exc).__name__}",
            details={"checkpoint": checkpoint, "fallback": "LocalPlanner remains available"},
        )

    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    from agent.orchestrator.openai_adapter import estimate_cost_usd

    cost = estimate_cost_usd(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        input_usd_per_million=config.input_usd_per_million,
        output_usd_per_million=config.output_usd_per_million,
    )
    if cost > SMOKE_CEILING_USD:
        return SmokeResult(
            ok=False,
            paid_call_attempted=True,
            openai_called=True,
            live_orders=False,
            message="Smoke exceeded $0.25 ceiling; usage was not recorded in the ledger.",
            details={
                "cost_usd": cost,
                "smoke_ceiling_usd": SMOKE_CEILING_USD,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "api_key_redacted": True,
            },
        )
    ledger.record(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
        model=config.model,
    )
    after = ledger.summary()
    text = str(getattr(response, "output_text", "") or "")[:500]
    return SmokeResult(
        ok=True,
        paid_call_attempted=True,
        openai_called=True,
        live_orders=False,
        message="Paid read-only smoke succeeded.",
        details={
            "model": config.model,
            "response_preview": text,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost,
            "smoke_ceiling_usd": SMOKE_CEILING_USD,
            "spent_usd_24h_before": before.get("spent_usd_24h"),
            "spent_usd_24h_after": after.get("spent_usd_24h"),
            "spent_usd_30d_after": after.get("spent_usd_30d"),
            "daily_budget_usd": config.daily_budget_usd,
            "monthly_budget_usd": config.monthly_budget_usd,
            "remaining_authorized_usd_est": max(
                0.0, float(config.monthly_budget_usd) - float(after.get("spent_usd_30d") or 0.0)
            ),
            "tools_used": [],
            "api_key_redacted": True,
        },
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="CryptoNova OpenAI orchestrator smoke test")
    parser.add_argument("--checkpoint", action="store_true", help="Print approval checkpoint only")
    parser.add_argument("--schema-only", action="store_true", help="Run offline schema smoke")
    parser.add_argument(
        "--approve",
        default="",
        help=f"Exact phrase {APPROVAL_PHRASE} required for a paid call",
    )
    args = parser.parse_args(argv)
    if args.checkpoint or (not args.schema_only and not args.approve):
        print(json.dumps(operator_approval_checkpoint(), indent=2))
        print("\nSTOP: no paid OpenAI call was made.")
        return 0
    if args.schema_only:
        result = run_schema_validation_smoke()
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.ok else 1
    result = run_paid_smoke(approval_phrase=args.approve)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
