"""
Read-only Bybit UNIFIED wallet snapshot for the operator dashboard.

Uses server-side API keys only. Never returns secrets or raw account fingerprints.
Does not place/cancel orders or change leverage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class WalletCoinBalance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coin: str
    wallet_balance: str
    equity: str
    available: str
    unrealised_pnl: str


class ExchangeWalletSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    source: str = "bybit"
    account_type: str = "UNIFIED"
    env_label: str
    is_mainnet: bool
    fetched_at: datetime
    total_equity: str | None = None
    total_wallet_balance: str | None = None
    total_available_balance: str | None = None
    total_perp_upl: str | None = None
    coins: list[WalletCoinBalance] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BybitWalletClient(Protocol):
    def get_wallet_balance(self, **kwargs: Any) -> dict[str, Any]: ...


def _dec_str(value: object) -> str | None:
    if value is None or value == "":
        return None
    try:
        return str(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_unified_wallet_response(
    response: dict[str, Any],
    *,
    env_label: str,
    is_mainnet: bool,
) -> ExchangeWalletSnapshot:
    if response.get("retCode") != 0:
        msg = str(response.get("retMsg") or "wallet_error")
        raise RuntimeError(f"bybit_wallet_error:{msg}")

    accounts = (response.get("result") or {}).get("list") or []
    if not accounts or not isinstance(accounts[0], dict):
        raise RuntimeError("bybit_wallet_empty")

    account = accounts[0]
    coins: list[WalletCoinBalance] = []
    for row in account.get("coin") or []:
        if not isinstance(row, dict):
            continue
        wallet = _dec_str(row.get("walletBalance")) or "0"
        try:
            if Decimal(wallet) == 0:
                continue
        except InvalidOperation:
            continue
        coin = str(row.get("coin") or "").strip()
        if not coin:
            continue
        available = (
            _dec_str(row.get("availableToWithdraw"))
            or _dec_str(row.get("equity"))
            or wallet
        )
        coins.append(
            WalletCoinBalance(
                coin=coin,
                wallet_balance=wallet,
                equity=_dec_str(row.get("equity")) or wallet,
                available=available,
                unrealised_pnl=_dec_str(row.get("unrealisedPnl")) or "0",
            )
        )

    notes = [
        "Read-only UNIFIED wallet snapshot. API keys never leave the server.",
        "This is not a trading endpoint.",
    ]
    if is_mainnet:
        notes.append("MAINNET — real funds. Prefer testnet/demo while learning.")

    return ExchangeWalletSnapshot(
        env_label=env_label,
        is_mainnet=is_mainnet,
        fetched_at=datetime.now(timezone.utc),
        total_equity=_dec_str(account.get("totalEquity")),
        total_wallet_balance=_dec_str(account.get("totalWalletBalance")),
        total_available_balance=_dec_str(account.get("totalAvailableBalance")),
        total_perp_upl=_dec_str(account.get("totalPerpUPL")),
        coins=coins,
        notes=notes,
    )


def fetch_unified_wallet(
    client: BybitWalletClient,
    *,
    env_label: str,
    is_mainnet: bool,
) -> ExchangeWalletSnapshot:
    response = client.get_wallet_balance(accountType="UNIFIED")
    if not isinstance(response, dict):
        raise RuntimeError("bybit_wallet_malformed")
    return parse_unified_wallet_response(
        response, env_label=env_label, is_mainnet=is_mainnet
    )


@dataclass(frozen=True)
class WalletFetchError:
    code: str
    message: str
