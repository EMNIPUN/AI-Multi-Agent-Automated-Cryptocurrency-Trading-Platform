"""
Phase 6A trading modes — independent of AGENT_ALLOW_LIVE / AGENT_DRY_RUN.

Default: SIGNALS_ONLY. MAINNET_TRADING has no active execution path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class TradingMode(str, Enum):
    SIGNALS_ONLY = "SIGNALS_ONLY"
    PAPER_TRADING = "PAPER_TRADING"
    TESTNET_TRADING = "TESTNET_TRADING"
    MAINNET_TRADING = "MAINNET_TRADING"  # locked — never activated in 6A


class MarketSegment(str, Enum):
    SPOT = "spot"
    LINEAR = "linear"  # USDT perpetual — auto-exec disabled until approved


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


def parse_trading_mode(raw: str | None = None) -> TradingMode:
    text = (raw if raw is not None else os.getenv("CRYPTONOVA_TRADING_MODE", "SIGNALS_ONLY")).strip()
    try:
        return TradingMode(text.upper())
    except ValueError:
        return TradingMode.SIGNALS_ONLY


@dataclass(frozen=True)
class AutomationGates:
    """
    Explicit dual gates for Testnet automation.

    Do NOT use AGENT_ALLOW_LIVE as a shortcut for Testnet or Mainnet.
    """

    mode: TradingMode
    testnet_trading_enabled: bool
    testnet_operator_approved: bool
    testnet_order_submission_approved: bool
    perpetual_auto_execution_enabled: bool
    mainnet_trading_enabled: bool  # must stay false
    bybit_testnet_env: bool
    bybit_demo_env: bool

    @property
    def testnet_mode_armed(self) -> bool:
        return (
            self.mode is TradingMode.TESTNET_TRADING
            and self.testnet_trading_enabled
            and self.testnet_operator_approved
            and self.bybit_testnet_env
            and not self.bybit_demo_env
            and not self.mainnet_trading_enabled
        )

    @property
    def order_submission_allowed(self) -> bool:
        """Live exchange order create — requires additional submission approval."""
        return (
            self.testnet_mode_armed
            and self.testnet_order_submission_approved
            and self.mode is not TradingMode.MAINNET_TRADING
        )

    @property
    def spot_auto_exec_allowed(self) -> bool:
        return self.order_submission_allowed

    @property
    def linear_auto_exec_allowed(self) -> bool:
        return self.order_submission_allowed and self.perpetual_auto_execution_enabled

    @property
    def mainnet_execution_path_exists(self) -> bool:
        return False  # hard lock for Phase 6A


def get_automation_gates() -> AutomationGates:
    return AutomationGates(
        mode=parse_trading_mode(),
        testnet_trading_enabled=_flag("TESTNET_TRADING_ENABLED"),
        testnet_operator_approved=_flag("TESTNET_TRADING_OPERATOR_APPROVED"),
        testnet_order_submission_approved=_flag("TESTNET_ORDER_SUBMISSION_APPROVED"),
        perpetual_auto_execution_enabled=_flag("PERPETUAL_AUTO_EXECUTION_ENABLED"),
        mainnet_trading_enabled=_flag("MAINNET_TRADING_ENABLED"),
        bybit_testnet_env=_flag("BYBIT_TESTNET", "true"),
        bybit_demo_env=_flag("BYBIT_DEMO"),
    )


def gates_public_dict() -> dict[str, object]:
    g = get_automation_gates()
    return {
        "mode": g.mode.value,
        "testnet_trading_enabled": g.testnet_trading_enabled,
        "testnet_operator_approved": g.testnet_operator_approved,
        "testnet_order_submission_approved": g.testnet_order_submission_approved,
        "testnet_mode_armed": g.testnet_mode_armed,
        "order_submission_allowed": g.order_submission_allowed,
        "spot_auto_exec_allowed": g.spot_auto_exec_allowed,
        "linear_auto_exec_allowed": g.linear_auto_exec_allowed,
        "perpetual_auto_execution_enabled": g.perpetual_auto_execution_enabled,
        "mainnet_trading_enabled": g.mainnet_trading_enabled,
        "mainnet_execution_path_exists": g.mainnet_execution_path_exists,
        "bybit_testnet_env": g.bybit_testnet_env,
        "bybit_demo_env": g.bybit_demo_env,
        "agent_allow_live_not_used_as_shortcut": True,
        "default_mode": TradingMode.SIGNALS_ONLY.value,
        "note": (
            "Phase 6A foundation — SIGNALS_ONLY by default. "
            "No Testnet orders until dual Testnet gates + TESTNET_ORDER_SUBMISSION_APPROVED. "
            "MAINNET_TRADING has no execution path."
        ),
    }


class AutomationGateError(RuntimeError):
    """Fail-closed gate violation."""
