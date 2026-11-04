"""Bybit orderLinkId helpers — deterministic, length-safe client order IDs."""

from __future__ import annotations

import hashlib
import re

# Bybit V5 orderLinkId: user-customized, max length 36.
ORDER_LINK_ID_MAX_LEN = 36
_ORDER_LINK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,36}$")


def env_scope_id(*, use_testnet: bool, use_demo: bool) -> str:
    """Non-secret environment identity for intent scoping."""
    if use_demo:
        return "demo"
    if use_testnet:
        return "testnet"
    return "mainnet"


def account_fingerprint(api_key: str) -> str:
    """Non-reversible short fingerprint of the API key (never store the key)."""
    material = (api_key or "").strip().encode("utf-8")
    if not material:
        return "nokey"
    return hashlib.sha256(material).hexdigest()[:12]


def validate_order_link_id(value: str) -> bool:
    return bool(value) and bool(_ORDER_LINK_ID_RE.fullmatch(value))


def build_client_order_id(fingerprint: str) -> str:
    """
    Derive a stable orderLinkId from an intent fingerprint.

    Format: 'i' + 32 hex chars = 33 characters (within Bybit's 36 limit).
    """
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    client_id = "i" + digest[:32]
    if not validate_order_link_id(client_id):
        raise ValueError("generated orderLinkId failed validation")
    return client_id


def build_intent_id(fingerprint: str) -> str:
    """Internal durable intent id (not sent to Bybit)."""
    return hashlib.sha256(f"intent|{fingerprint}".encode("utf-8")).hexdigest()


def intent_fingerprint(
    *,
    env_scope: str,
    account_fp: str,
    category: str,
    symbol: str,
    side: str,
    qty: str,
    reduce_only: bool,
    take_profit: str | None,
    stop_loss: str | None,
    correlation_id: str,
) -> str:
    """
    Canonical fingerprint for one logical order intent.

    Same inputs => same client_order_id. Unrelated trades must differ in at
    least one field (typically correlation_id / qty / side).
    """
    parts = [
        env_scope,
        account_fp,
        category.lower(),
        symbol.upper(),
        side,
        qty,
        "1" if reduce_only else "0",
        take_profit or "",
        stop_loss or "",
        correlation_id,
    ]
    return "|".join(parts)
