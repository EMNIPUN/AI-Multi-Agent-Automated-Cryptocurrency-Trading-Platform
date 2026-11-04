"""Server-side API configuration. Never place secrets in Next.js public env."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from apps.api.app.database_url import (
    DatabaseUrlError,
    DatabaseUrlInfo,
    inspect_database_url,
    normalize_database_url,
    redact_database_url,
)


def _split_origins(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text or text == "*":
        # Explicitly reject wildcard — empty list means CORS middleware off.
        return []
    return [part.strip() for part in text.split(",") if part.strip() and part.strip() != "*"]


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Multi-Agent Crypto Trading API"
    app_version: str = "0.3.0-phase3a"
    app_env: str = Field(default="development", validation_alias="API_APP_ENV")

    api_host: str = Field(default="127.0.0.1", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")
    api_debug: bool = Field(default=False, validation_alias="API_DEBUG")

    # Comma-separated explicit origins only. Empty / "*" → no CORS (no wildcard).
    # NoDecode: empty env value "" must not be JSON-parsed by pydantic-settings.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list, validation_alias="API_CORS_ORIGINS"
    )

    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    database_ssl_require: bool = Field(
        default=True, validation_alias="DATABASE_SSL_REQUIRE"
    )

    # --- Supabase Auth (server-side only; never NEXT_PUBLIC_ JWT secrets) ---
    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    # jwks (preferred asymmetric) | hs256 (legacy JWT secret, server-only)
    auth_jwt_mode: str = Field(default="jwks", validation_alias="AUTH_JWT_MODE")
    supabase_jwt_audience: str = Field(
        default="authenticated", validation_alias="SUPABASE_JWT_AUDIENCE"
    )
    supabase_jwt_issuer: str | None = Field(
        default=None, validation_alias="SUPABASE_JWT_ISSUER"
    )
    supabase_jwks_url: str | None = Field(
        default=None, validation_alias="SUPABASE_JWKS_URL"
    )
    # Legacy HS256 only — never place in frontend env.
    supabase_jwt_secret: str | None = Field(
        default=None, validation_alias="SUPABASE_JWT_SECRET"
    )
    auth_jwt_leeway_seconds: int = Field(
        default=30, validation_alias="AUTH_JWT_LEEWAY_SECONDS"
    )
    # Real private row reads stay off until ownership/tenant schema + RLS ship.
    private_data_reads_enabled: bool = Field(
        default=False, validation_alias="PRIVATE_DATA_READS_ENABLED"
    )
    # Phase 3A: labeled SAMPLE snapshots for Command Center (default on).
    observability_fixture_mode: bool = Field(
        default=True, validation_alias="OBSERVABILITY_FIXTURE_MODE"
    )
    # Live SSE requires ownership migration + PRIVATE_DATA_READS_ENABLED (default off).
    observability_live_stream_enabled: bool = Field(
        default=False, validation_alias="OBSERVABILITY_LIVE_STREAM_ENABLED"
    )
    # Separate append-only worker ledger. Empty keeps worker snapshots unavailable.
    observability_ledger_path: str | None = Field(
        default=None, validation_alias="OBSERVABILITY_LEDGER_PATH"
    )
    # Read-only Bybit UNIFIED wallet for local Command Center (keys stay server-side).
    exchange_wallet_reads_enabled: bool = Field(
        default=True, validation_alias="EXCHANGE_WALLET_READS_ENABLED"
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, value: object) -> list[str]:
        return _split_origins(value if isinstance(value, (str, list)) or value is None else str(value))

    @field_validator("api_host", mode="before")
    @classmethod
    def _default_loopback(cls, value: object) -> str:
        text = str(value or "").strip() or "127.0.0.1"
        # Discourage binding all interfaces in early phases.
        if text in {"0.0.0.0", "::", "[::]"}:
            return "127.0.0.1"
        return text

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url and self.database_url.strip())

    def require_database_url(self) -> str:
        if not self.database_configured:
            raise DatabaseUrlError(
                "DATABASE_URL is not set. Configure a server-side Postgres URL "
                "(Supabase Direct or Session pooler) before using DB features or Alembic."
            )
        return self.database_url.strip()  # type: ignore[union-attr]

    def sqlalchemy_url(self) -> str:
        raw = self.require_database_url()
        try:
            return normalize_database_url(
                raw, require_ssl_for_remote=self.database_ssl_require
            )
        except DatabaseUrlError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DatabaseUrlError("DATABASE_URL could not be normalized") from exc

    def database_url_info(self) -> DatabaseUrlInfo:
        return inspect_database_url(
            self.require_database_url(),
            require_ssl_for_remote=self.database_ssl_require,
        )

    def redacted_database_url(self) -> str:
        if not self.database_configured:
            return ""
        try:
            return redact_database_url(self.sqlalchemy_url())
        except DatabaseUrlError:
            return "<invalid>"

    def remote_database_requires_ssl(self) -> bool:
        if not self.database_configured:
            return False
        info = self.database_url_info()
        return info.is_remote and bool(self.database_ssl_require)

    def engine_connect_args(self) -> dict:
        """TLS for remote Supabase/Postgres. Localhost left alone for offline tests."""
        if not self.remote_database_requires_ssl():
            return {}
        # psycopg3 also honors sslmode in the URL; keep connect_args as belt-and-suspenders.
        return {"sslmode": "require"}

    def resolved_supabase_url(self) -> str:
        return (self.supabase_url or "").strip().rstrip("/")

    def resolved_jwt_issuer(self) -> str:
        if self.supabase_jwt_issuer and self.supabase_jwt_issuer.strip():
            return self.supabase_jwt_issuer.strip().rstrip("/")
        base = self.resolved_supabase_url()
        if not base:
            return ""
        return f"{base}/auth/v1"

    def resolved_jwks_url(self) -> str:
        if self.supabase_jwks_url and self.supabase_jwks_url.strip():
            return self.supabase_jwks_url.strip()
        base = self.resolved_supabase_url()
        if not base:
            return ""
        return f"{base}/auth/v1/.well-known/jwks.json"

    def auth_settings_for_verifier(self) -> "ApiSettings":
        """Return settings with issuer/jwks resolved for the verifier factory."""
        # Mutating copy via model_copy keeps cache of get_api_settings intact.
        return self.model_copy(
            update={
                "supabase_jwt_issuer": self.resolved_jwt_issuer(),
                "supabase_jwks_url": self.resolved_jwks_url(),
            }
        )


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()


def clear_settings_cache() -> None:
    get_api_settings.cache_clear()


def bybit_env_label_safe() -> str:
    """Non-secret exchange environment label (no keys)."""
    demo = os.getenv("BYBIT_DEMO", "false").strip().lower() in {"1", "true", "yes"}
    testnet = os.getenv("BYBIT_TESTNET", "true").strip().lower() in {"1", "true", "yes"}
    if demo:
        return "demo"
    return "testnet" if testnet else "mainnet"


def agent_dry_run_default() -> bool:
    return os.getenv("AGENT_DRY_RUN", "true").strip().lower() in {"1", "true", "yes"}


def agent_allow_live_default() -> bool:
    return os.getenv("AGENT_ALLOW_LIVE", "false").strip().lower() in {"1", "true", "yes"}
