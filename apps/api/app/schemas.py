"""Pydantic response schemas — public-safe fields only."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str


class SystemStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str
    version: str
    app_env: str
    api_bind_host: str
    read_only_api: bool = True
    trading_http_endpoints_enabled: bool = False
    authentication_required_for_private_data: bool = True
    private_data_routes_enabled: bool = False
    supabase_auth_configured: bool = False
    private_catalog_reads_enabled: bool = False
    database_configured: bool
    database_ssl_enforced_for_remote: bool
    bybit_env: str = Field(description="testnet | demo | mainnet (label only)")
    agent_dry_run_default: bool
    agent_allow_live_default: bool
    execution_source_of_truth: str = (
        "local_sqlite_order_intents_and_risk — not mirrored to Postgres as authority"
    )
    cors_origins_configured: int = Field(
        description="Count of explicit CORS origins (0 = CORS disabled; never '*')"
    )


class MeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    role: str
    email: str | None = None
    scopes: list[str] = Field(default_factory=list)
    private_data_reads_enabled: bool = False
    ownership_enforced: bool = False


class PaginationQuery(BaseModel):
    """Strict pagination bounds for authorized list endpoints."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=1_000_000)

    @field_validator("limit", "offset", mode="before")
    @classmethod
    def _coerce_int(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("invalid")
        return value


class DisabledCatalogResponse(BaseModel):
    """Returned only if we choose 200 stubs — Phase 2C uses HTTP 403 instead."""

    detail: str = "ownership_schema_required"
    items: list[dict] = Field(default_factory=list)


class AgentDecisionItem(BaseModel):
    """Public decision row — omits account_fp and other raw account identifiers."""

    model_config = ConfigDict(extra="forbid")

    id: str
    created_at: datetime
    env_scope: str
    symbol: str
    category: str
    action: str
    strategy_id: str
    signal_id: str | None = None
    correlation_id: str | None = None
    reason: str = ""
    payload_json: dict[str, Any] | list[Any] | None = None


class AgentDecisionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AgentDecisionItem]
    limit: int
    offset: int


class SystemEventItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    created_at: datetime
    env_scope: str
    severity: str
    event_type: str
    message: str
    details_json: dict[str, Any] | list[Any] | None = None


class SystemEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SystemEventItem]
    limit: int
    offset: int


class StrategyConfigItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    created_at: datetime
    updated_at: datetime
    name: str
    version: str
    enabled: bool
    config_json: dict[str, Any] | list[Any] | None = None


class StrategyConfigListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StrategyConfigItem]
    limit: int
    offset: int
