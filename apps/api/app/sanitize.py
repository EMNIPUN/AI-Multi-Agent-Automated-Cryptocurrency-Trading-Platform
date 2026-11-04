"""
Public-safe JSON sanitization for catalog API responses.

Never return secrets, credentials, or raw account identifiers to the browser.
Defense in depth — writers should also avoid storing secrets in JSON columns.
"""

from __future__ import annotations

from typing import Any

# Substring match (case-insensitive) against object keys.
_SENSITIVE_KEY_FRAGMENTS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_key",
        "private_key",
        "privatekey",
        "credential",
        "authorization",
        "bearer",
        "cookie",
        "session_id",
        "refresh",
        "jwt",
        "signing",
        "webhook",
        "account_fp",
        "account_id",
        "api_secret",
        "bybit",
        "supabase_service",
        "service_role",
        "database_url",
        "dsn",
    }
)

_REDACTED = "[redacted]"
_MAX_DEPTH = 8
_MAX_LIST = 50
_MAX_DICT_KEYS = 40
_MAX_STRING = 2_000


def _key_sensitive(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    if lowered in _SENSITIVE_KEY_FRAGMENTS:
        return True
    return any(frag in lowered for frag in _SENSITIVE_KEY_FRAGMENTS)


def sanitize_public_json(value: Any, *, _depth: int = 0) -> Any:
    """Return a JSON-serializable structure safe for browser clients."""
    if value is None:
        return None
    if _depth > _MAX_DEPTH:
        return "[truncated]"
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        if len(value) > _MAX_STRING:
            return value[:_MAX_STRING] + "…"
        return value
    if isinstance(value, list):
        return [
            sanitize_public_json(item, _depth=_depth + 1)
            for item in value[:_MAX_LIST]
        ]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for i, (raw_key, raw_val) in enumerate(value.items()):
            if i >= _MAX_DICT_KEYS:
                out["_truncated"] = True
                break
            key = str(raw_key)
            if _key_sensitive(key):
                out[key] = _REDACTED
            else:
                out[key] = sanitize_public_json(raw_val, _depth=_depth + 1)
        return out
    # Unsupported types (bytes, custom) — never leak repr of secrets.
    return _REDACTED
