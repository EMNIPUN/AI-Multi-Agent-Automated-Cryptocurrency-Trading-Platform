"""Server-only Bybit credential_ref resolution (never expose secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from fastapi import HTTPException

from apps.api.app.exchange.bindings import ExchangeEnvironment
from pybit.unified_trading import HTTP


@dataclass(frozen=True, slots=True)
class ResolvedBybitCredentials:
    """In-memory only — never serialize to API/logs/telemetry."""

    api_key: str
    api_secret: str
    environment: ExchangeEnvironment
    label: str
    credential_ref: str


@dataclass(frozen=True, slots=True)
class _RefSpec:
    key_env: str
    secret_env: str
    environment: ExchangeEnvironment
    label: str


# Explicit allowlist — credential_ref never contains raw keys.
# Env var names are fixed here; clients cannot inject variable names.
_REF_SPECS: dict[str, _RefSpec] = {
    "env:BYBIT_OPERATOR": _RefSpec(
        key_env="BYBIT_API_KEY",
        secret_env="BYBIT_API_SECRET",
        environment=ExchangeEnvironment.MAINNET,  # overridden by process flags
        label="Operator default",
    ),
    "env:BYBIT_TESTNET_OPERATOR": _RefSpec(
        key_env="BYBIT_TESTNET_API_KEY",
        secret_env="BYBIT_TESTNET_API_SECRET",
        environment=ExchangeEnvironment.TESTNET,
        label="Operator testnet",
    ),
    "env:BYBIT_MAINNET_OPERATOR": _RefSpec(
        key_env="BYBIT_MAINNET_API_KEY",
        secret_env="BYBIT_MAINNET_API_SECRET",
        environment=ExchangeEnvironment.MAINNET,
        label="Operator mainnet",
    ),
    "env:BYBIT_DEMO_OPERATOR": _RefSpec(
        key_env="BYBIT_DEMO_API_KEY",
        secret_env="BYBIT_DEMO_API_SECRET",
        environment=ExchangeEnvironment.DEMO,
        label="Operator demo",
    ),
}

ALLOWLISTED_CREDENTIAL_REFS: frozenset[str] = frozenset(_REF_SPECS)


def is_allowlisted_credential_ref(credential_ref: str) -> bool:
    return (credential_ref or "").strip() in ALLOWLISTED_CREDENTIAL_REFS


def _process_default_environment(environ: Mapping[str, str]) -> ExchangeEnvironment:
    demo = environ.get("BYBIT_DEMO", "false").strip().lower() in {"1", "true", "yes"}
    testnet = environ.get("BYBIT_TESTNET", "true").strip().lower() in {"1", "true", "yes"}
    if demo:
        return ExchangeEnvironment.DEMO
    if testnet:
        return ExchangeEnvironment.TESTNET
    return ExchangeEnvironment.MAINNET


def resolve_credential_ref(
    credential_ref: str,
    *,
    expected_environment: ExchangeEnvironment,
    environ: Mapping[str, str] | None = None,
) -> ResolvedBybitCredentials:
    """
    Resolve opaque credential_ref to server-side Bybit credentials.

    Raises HTTPException on missing/mismatched/unknown refs. Never returns secrets
    in exception details.
    """
    env_map = environ if environ is not None else os.environ
    ref = (credential_ref or "").strip()
    # Reject injection-shaped refs before allowlist miss (no dynamic getenv of client input).
    if any(ch in ref for ch in ("$", "{", "}", "`", ";", "|", "\n", "\r", "\\")):
        raise HTTPException(status_code=403, detail="credential_ref_invalid")
    if not ref or ref not in _REF_SPECS:
        raise HTTPException(status_code=403, detail="credential_ref_unknown")

    spec = _REF_SPECS[ref]
    # Defense: never read env keys from the credential_ref string itself.
    assert spec.key_env in {
        "BYBIT_API_KEY",
        "BYBIT_TESTNET_API_KEY",
        "BYBIT_MAINNET_API_KEY",
        "BYBIT_DEMO_API_KEY",
    }
    resolved_env = (
        _process_default_environment(env_map)
        if ref == "env:BYBIT_OPERATOR"
        else spec.environment
    )
    if resolved_env is not expected_environment:
        raise HTTPException(status_code=403, detail="credential_environment_mismatch")

    # Prefer env-specific keys; for default operator ref also accept BYBIT_* pair.
    key = (env_map.get(spec.key_env) or "").strip()
    secret = (env_map.get(spec.secret_env) or "").strip()
    if ref == "env:BYBIT_OPERATOR" and (not key or not secret):
        key = (env_map.get("BYBIT_API_KEY") or "").strip()
        secret = (env_map.get("BYBIT_API_SECRET") or "").strip()

    if not key or not secret:
        raise HTTPException(status_code=503, detail="credential_material_unavailable")

    return ResolvedBybitCredentials(
        api_key=key,
        api_secret=secret,
        environment=resolved_env,
        label=spec.label,
        credential_ref=ref,
    )


def build_bybit_wallet_client(creds: ResolvedBybitCredentials) -> HTTP:
    """Construct a read-oriented Bybit HTTP client for the resolved environment."""
    from apps.api.app.exchange.bybit_clock import (
        install_pybit_timestamp_patch,
        sync_bybit_clock,
    )

    install_pybit_timestamp_patch()
    sync_bybit_clock(force=False)
    return HTTP(
        testnet=creds.environment is ExchangeEnvironment.TESTNET,
        demo=creds.environment is ExchangeEnvironment.DEMO,
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        timeout=30,
        force_retry=True,
        max_retries=5,
        retry_delay=1,
        recv_window=20000,
    )


def env_label_for(environment: ExchangeEnvironment) -> str:
    if environment is ExchangeEnvironment.DEMO:
        return "Demo Trading"
    if environment is ExchangeEnvironment.TESTNET:
        return "Testnet"
    return "Mainnet"
