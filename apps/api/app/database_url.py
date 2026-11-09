"""
Safe DATABASE_URL normalization for Supabase Postgres (psycopg3).

Never log the return value of parse/normalize helpers that retain passwords.
Use redact_database_url() for any operator-facing message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlunparse

APP_SCHEMA = "app"

# Soft classification only — hosts come from env, never hardcoded project refs.
_SUPABASE_HOST_MARKERS = ("supabase.co", "supabase.com", "pooler.supabase")


class DatabaseUrlError(ValueError):
    """Configuration error — message must not include secrets."""


@dataclass(frozen=True)
class DatabaseUrlInfo:
    driver: str
    host: str
    port: int | None
    database: str
    user: str
    is_remote: bool
    is_supabase_like: bool
    pooler_hint: str  # "session_pooler" | "transaction_pooler" | "direct" | "unknown"
    sslmode: str | None
    redacted_url: str


_CONNECTION_STRING = re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s\"'`<>]+", re.IGNORECASE)


def redact_connection_strings(value: str) -> str:
    """Replace any Postgres URL embedded in an error or log line."""

    def _one(match: re.Match[str]) -> str:
        try:
            return redact_database_url(match.group(0))
        except Exception:  # noqa: BLE001 — never return the original URL
            return "postgresql://***"

    return _CONNECTION_STRING.sub(_one, value)


def redact_database_url(url: str) -> str:
    """Replace password with *** for logs/errors."""
    try:
        parsed = urlparse(url)
    except Exception as exc:  # noqa: BLE001
        raise DatabaseUrlError("DATABASE_URL is malformed") from exc
    if not parsed.scheme or not parsed.netloc:
        return "<unparseable>"
    user = unquote(parsed.username) if parsed.username else ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    auth = f"{user}:***@" if user or parsed.password else ""
    path = parsed.path or ""
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{auth}{host}{port}{path}{query}"


def _normalize_scheme(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql+psycopg://" + url[len("postgresql+psycopg2://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgresql+psycopg://"):
        return url
    raise DatabaseUrlError(
        "DATABASE_URL must use postgres://, postgresql://, or postgresql+psycopg://"
    )


def _encode_userinfo(user: str | None, password: str | None) -> str:
    if user is None and password is None:
        return ""
    u = quote(unquote(user or ""), safe="")
    if password is None:
        return f"{u}@"
    # Password may already be percent-encoded; unquote once then re-quote.
    p = quote(unquote(password), safe="")
    return f"{u}:{p}@"


def _pooler_hint(host: str, port: int | None) -> str:
    h = host.lower()
    if "pooler" in h:
        # Supabase: 6543 often transaction pooler; 5432 session pooler on pooler host.
        if port == 6543:
            return "transaction_pooler"
        if port == 5432:
            return "session_pooler"
        return "session_pooler"
    if "supabase" in h and port == 5432:
        return "direct"
    return "unknown"


def normalize_database_url(raw: str, *, require_ssl_for_remote: bool = True) -> str:
    """
    Normalize to postgresql+psycopg:// and ensure sslmode=require for remote hosts.

    Supports Direct and Session/Transaction pooler URLs supplied via env — no
    hardcoded project hosts.
    """
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        raise DatabaseUrlError("DATABASE_URL is empty")
    if "user:pass@localhost" in text or text.startswith("driver://"):
        raise DatabaseUrlError("DATABASE_URL looks like a placeholder")

    url = _normalize_scheme(text)
    try:
        parsed = urlparse(url)
    except Exception as exc:  # noqa: BLE001
        raise DatabaseUrlError("DATABASE_URL is malformed") from exc

    host = (parsed.hostname or "").lower()
    if not host:
        raise DatabaseUrlError("DATABASE_URL is missing a host")

    userinfo = _encode_userinfo(parsed.username, parsed.password)
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{userinfo}{host}{port}"

    query_pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    is_local = host in {"localhost", "127.0.0.1", "::1"}
    if require_ssl_for_remote and not is_local:
        # Prefer require (verify-full can be set by operator in URL if desired).
        mode = (query_pairs.get("sslmode") or "").lower()
        if mode in {"", "disable", "allow", "prefer"}:
            query_pairs["sslmode"] = "require"

    new_query = urlencode(query_pairs)
    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path or "/postgres",
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def inspect_database_url(raw: str, *, require_ssl_for_remote: bool = True) -> DatabaseUrlInfo:
    normalized = normalize_database_url(
        raw, require_ssl_for_remote=require_ssl_for_remote
    )
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower()
    is_local = host in {"localhost", "127.0.0.1", "::1"}
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    return DatabaseUrlInfo(
        driver=parsed.scheme,
        host=host,
        port=parsed.port,
        database=(parsed.path or "/").lstrip("/") or "postgres",
        user=unquote(parsed.username) if parsed.username else "",
        is_remote=not is_local,
        is_supabase_like=any(m in host for m in _SUPABASE_HOST_MARKERS),
        pooler_hint=_pooler_hint(host, parsed.port),
        sslmode=q.get("sslmode"),
        redacted_url=redact_database_url(normalized),
    )
