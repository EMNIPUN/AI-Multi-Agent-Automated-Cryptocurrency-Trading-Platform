"""Read-only exchange wallet HTTP contract for the Command Center."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.exchange.access import ExchangeReadMode, resolve_exchange_read_context
from apps.api.app.exchange.credentials import (
    build_bybit_wallet_client,
    env_label_for,
    resolve_credential_ref,
)
from apps.api.app.exchange.wallet import ExchangeWalletSnapshot, fetch_unified_wallet

router = APIRouter(prefix="/api/v1/exchange", tags=["exchange"])


def _build_operator_local_session():
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

    Access modes:
    - Operator-local diagnostic (no Authorization, loopback peer only).
    - Owner-bound authenticated read (JWT + active binding + PRIVATE_DATA_READS
      + credential_ref resolver).

    Never returns API keys. No order placement.
    """
    if not settings.exchange_wallet_reads_enabled:
        raise HTTPException(status_code=403, detail="exchange_wallet_reads_disabled")

    # Fix Windows clock skew vs Bybit before signed wallet reads (ErrCode 10002).
    try:
        from apps.api.app.exchange.bybit_clock import (
            install_pybit_timestamp_patch,
            sync_bybit_clock,
        )

        install_pybit_timestamp_patch()
        sync_bybit_clock(force=True)
    except Exception:  # noqa: BLE001
        pass

    ctx = resolve_exchange_read_context(request, settings)

    override = getattr(request.app.state, "bybit_wallet_client", None)
    ref_clients = getattr(request.app.state, "bybit_wallet_clients", None) or {}

    try:
        if ctx.mode is ExchangeReadMode.OWNER_BOUND:
            if ctx.binding is None:
                raise HTTPException(status_code=403, detail="exchange_binding_missing")
            ref = ctx.binding.credential_ref
            if ref in ref_clients:
                client = ref_clients[ref]
                label = env_label_for(ctx.binding.environment)
                mainnet = ctx.binding.environment.value == "mainnet"
            else:
                creds = resolve_credential_ref(
                    ref, expected_environment=ctx.binding.environment
                )
                client = build_bybit_wallet_client(creds)
                label = env_label_for(creds.environment)
                mainnet = creds.environment.value == "mainnet"
            snap = fetch_unified_wallet(client, env_label=label, is_mainnet=mainnet)
            # Annotate ownership without secrets.
            return snap.model_copy(
                update={
                    "notes": list(snap.notes)
                    + [
                        "Owner-bound wallet read.",
                        f"binding_environment={ctx.binding.environment.value}",
                    ]
                }
            )

        # Operator-local diagnostic path.
        if override is not None:
            client = override
            label = "fixture"
            mainnet = False
        else:
            from bot.config import env_label as bybit_env_label
            from bot.config import is_live_mainnet

            client = _build_operator_local_session()
            label = bybit_env_label()
            mainnet = is_live_mainnet()
        return fetch_unified_wallet(client, env_label=label, is_mainnet=mainnet)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — fail closed; no secrets in detail
        raise HTTPException(
            status_code=503,
            detail="bybit_wallet_unavailable",
        ) from exc
