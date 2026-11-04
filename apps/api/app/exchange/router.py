"""Read-only exchange wallet HTTP contract for the Command Center."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.exchange.wallet import ExchangeWalletSnapshot, fetch_unified_wallet

router = APIRouter(prefix="/api/v1/exchange", tags=["exchange"])


def _build_bybit_session():
    from bot.client import create_session
    from bot.config import API_KEY, API_SECRET

    if not API_KEY or not API_SECRET:
        raise HTTPException(status_code=503, detail="bybit_credentials_missing")
    return create_session()


@router.get("/wallet", response_model=ExchangeWalletSnapshot)
def get_exchange_wallet(
    request: Request,
    settings: ApiSettings = Depends(get_api_settings),
) -> ExchangeWalletSnapshot:
    """
    UNIFIED wallet balances using server-side Bybit keys.

    Disabled unless EXCHANGE_WALLET_READS_ENABLED=true.
    Never returns API keys. No order placement.
    """
    if not settings.exchange_wallet_reads_enabled:
        raise HTTPException(status_code=403, detail="exchange_wallet_reads_disabled")

    override = getattr(request.app.state, "bybit_wallet_client", None)
    if override is not None:
        client = override
        label = "fixture"
        mainnet = False
    else:
        from bot.config import env_label as bybit_env_label
        from bot.config import is_live_mainnet

        client = _build_bybit_session()
        label = bybit_env_label()
        mainnet = is_live_mainnet()

    try:
        return fetch_unified_wallet(
            client, env_label=label, is_mainnet=mainnet
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — fail closed; no secrets in detail
        raise HTTPException(
            status_code=503,
            detail="bybit_wallet_unavailable",
        ) from exc
