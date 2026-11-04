"""Account risk mode state machine (Phase 1C)."""

from __future__ import annotations

from enum import Enum


class AccountRiskMode(str, Enum):
    NORMAL = "NORMAL"
    REDUCE_ONLY = "REDUCE_ONLY"
    HALTED = "HALTED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


# Modes that may authorize exposure-increasing orders.
EXPOSURE_ALLOWED_MODES = frozenset({AccountRiskMode.NORMAL})

# Modes that may authorize reduce-only / protective closes.
REDUCE_ALLOWED_MODES = frozenset(
    {
        AccountRiskMode.NORMAL,
        AccountRiskMode.REDUCE_ONLY,
        AccountRiskMode.HALTED,
        AccountRiskMode.RECOVERY_REQUIRED,
    }
)


def allows_new_exposure(mode: AccountRiskMode) -> bool:
    return mode in EXPOSURE_ALLOWED_MODES


def allows_reduce_only(mode: AccountRiskMode) -> bool:
    return mode in REDUCE_ALLOWED_MODES
