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
from apps.api.app.runtime_db import resolve_application_database_url


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
    # Part 6A: binding list/create/revoke HTTP. Persistence to Postgres stays off
    # until separate operator approval (in-memory fixture store only).
    exchange_binding_api_enabled: bool = Field(
        default=True, validation_alias="EXCHANGE_BINDING_API_ENABLED"
    )
    exchange_binding_persistence_enabled: bool = Field(
        default=False, validation_alias="EXCHANGE_BINDING_PERSISTENCE_ENABLED"
    )
    # Part 6C: second gate — persistence flag alone must not write to Postgres.
    exchange_binding_persistence_operator_approved: bool = Field(
        default=False,
        validation_alias="EXCHANGE_BINDING_PERSISTENCE_OPERATOR_APPROVED",
    )
    # Phase 4D — Supabase signal persistence (independent of binding persistence).
    signal_supabase_writes_enabled: bool = Field(
        default=False, validation_alias="SIGNAL_SUPABASE_WRITES_ENABLED"
    )
    signal_supabase_writes_operator_approved: bool = Field(
        default=False,
        validation_alias="SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED",
    )
    signal_cloud_sync_enabled: bool = Field(
        default=False, validation_alias="SIGNAL_CLOUD_SYNC_ENABLED"
    )
    # Option A — least-privilege runtime DB (DISABLED until remote security gate).
    # When false (default): FastAPI keeps using DATABASE_URL; no GUC identity attach.
    runtime_db_identity_enabled: bool = Field(
        default=False, validation_alias="RUNTIME_DB_IDENTITY_ENABLED"
    )
    # Future separate credential for cryptonova_api_runtime — unused until approved.
    database_runtime_url: str | None = Field(
        default=None, validation_alias="DATABASE_RUNTIME_URL"
    )
    database_migrator_url: str | None = Field(
        default=None, validation_alias="DATABASE_MIGRATOR_URL"
    )
    # Prompt 65B — local paper journal read API (DISABLED by default).
    # When false: status reports disabled; session/account routes return 503.
    # Never mutates paper DB; never auto-attaches broker.
    paper_read_api_enabled: bool = Field(
        default=False, validation_alias="PAPER_READ_API_ENABLED"
    )
    paper_sqlite_path: str | None = Field(
        default=None, validation_alias="PAPER_SQLITE_PATH"
    )
    # Prompt 68B — local backtest artifact READ API (DISABLED by default).
    # GET-only discovery of saved 68A JSON reports; never runs a backtest.
    backtest_read_api_enabled: bool = Field(
        default=False, validation_alias="BACKTEST_READ_API_ENABLED"
    )
    backtest_results_dir: str | None = Field(
        default=None, validation_alias="BACKTEST_RESULTS_DIR"
    )
    # Prompt 68C — controlled historical backtest RUN API (DISABLED by default).
    # Explicit POST only; never enables live exchange execution.
    backtest_run_api_enabled: bool = Field(
        default=False, validation_alias="BACKTEST_RUN_API_ENABLED"
    )
    backtest_max_candles_per_run: int = Field(
        default=5000, validation_alias="BACKTEST_MAX_CANDLES_PER_RUN"
    )
    backtest_max_range_ms: int = Field(
        default=7_776_000_000, validation_alias="BACKTEST_MAX_RANGE_MS"
    )  # 90 days
    backtest_max_simultaneous_runs: int = Field(
        default=1, validation_alias="BACKTEST_MAX_SIMULTANEOUS_RUNS"
    )
    backtest_max_queued_runs: int = Field(
        default=2, validation_alias="BACKTEST_MAX_QUEUED_RUNS"
    )
    backtest_max_runtime_seconds: int = Field(
        default=600, validation_alias="BACKTEST_MAX_RUNTIME_SECONDS"
    )
    # SQLite → Supabase SoT cutover: agent stores use Postgres when true (default).
    supabase_sot_enabled: bool = Field(
        default=True, validation_alias="SUPABASE_SOT_ENABLED"
    )
    # Prompt 69A — news intelligence (DEFAULT OFF; advisory storage only).
    news_read_api_enabled: bool = Field(
        default=False, validation_alias="NEWS_READ_API_ENABLED"
    )
    news_collection_enabled: bool = Field(
        default=False, validation_alias="NEWS_COLLECTION_ENABLED"
    )
    news_alerts_enabled: bool = Field(
        default=False, validation_alias="NEWS_ALERTS_ENABLED"
    )
    news_llm_enabled: bool = Field(
        default=False, validation_alias="NEWS_LLM_ENABLED"
    )
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    cryptonova_llm_model: str | None = Field(
        default=None, validation_alias="CRYPTONOVA_LLM_MODEL"
    )
    cryptonova_llm_timeout_seconds: float = Field(
        default=20.0, validation_alias="CRYPTONOVA_LLM_TIMEOUT_SECONDS"
    )
    cryptonova_llm_max_calls_per_hour: int = Field(
        default=20, validation_alias="CRYPTONOVA_LLM_MAX_CALLS_PER_HOUR"
    )
    cryptonova_llm_daily_budget_usd: float = Field(
        default=1.0, validation_alias="CRYPTONOVA_LLM_DAILY_BUDGET_USD"
    )
    news_agent_advisory_enabled: bool = Field(
        default=False, validation_alias="NEWS_AGENT_ADVISORY_ENABLED"
    )
    newsdata_api_key: str | None = Field(
        default=None, validation_alias="NEWSDATA_API_KEY"
    )
    news_rss_feed_urls: str | None = Field(
        default=None, validation_alias="NEWS_RSS_FEED_URLS"
    )
    news_telegram_enabled: bool = Field(
        default=False, validation_alias="NEWS_TELEGRAM_ENABLED"
    )
    news_telegram_bot_token: str | None = Field(
        default=None, validation_alias="NEWS_TELEGRAM_BOT_TOKEN"
    )
    news_telegram_chat_id: str | None = Field(
        default=None, validation_alias="NEWS_TELEGRAM_CHAT_ID"
    )
    news_auto_collection_enabled: bool = Field(
        default=False, validation_alias="NEWS_AUTO_COLLECTION_ENABLED"
    )
    news_collection_interval_seconds: int = Field(
        default=900, validation_alias="NEWS_COLLECTION_INTERVAL_SECONDS"
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

    def sqlalchemy_url_legacy(self) -> str:
        """Privileged / admin DATABASE_URL path (Alembic + pre-Gate-63 FastAPI)."""
        raw = self.require_database_url()
        try:
            return normalize_database_url(
                raw, require_ssl_for_remote=self.database_ssl_require
            )
        except DatabaseUrlError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DatabaseUrlError("DATABASE_URL could not be normalized") from exc

    def sqlalchemy_url(self) -> str:
        """
        Application engine URL.

        Default (RUNTIME_DB_IDENTITY_ENABLED=false): DATABASE_URL (unchanged behavior).
        Future least-privilege mode: DATABASE_RUNTIME_URL only — no silent fallback.
        """
        return resolve_application_database_url(self)

    def database_url_info(self) -> DatabaseUrlInfo:
        # Inspect the URL the application engine would actually use.
        if self.runtime_db_identity_enabled:
            raw = (self.database_runtime_url or "").strip()
            if not raw:
                raise DatabaseUrlError("database_runtime_url_required")
            return inspect_database_url(
                raw, require_ssl_for_remote=self.database_ssl_require
            )
        return inspect_database_url(
            self.require_database_url(),
            require_ssl_for_remote=self.database_ssl_require,
        )

    def redacted_database_url(self) -> str:
        if not self.database_configured and not (
            self.runtime_db_identity_enabled and (self.database_runtime_url or "").strip()
        ):
            return ""
        try:
            return redact_database_url(self.sqlalchemy_url())
        except DatabaseUrlError:
            return "<invalid>"

    def remote_database_requires_ssl(self) -> bool:
        try:
            info = self.database_url_info()
        except DatabaseUrlError:
            return False
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
