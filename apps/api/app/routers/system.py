"""Safe system status — non-sensitive metadata only."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.app.config import (
    ApiSettings,
    agent_allow_live_default,
    agent_dry_run_default,
    bybit_env_label_safe,
    get_api_settings,
)
from apps.api.app.schemas import SystemStatusResponse

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def system_status(
    settings: ApiSettings = Depends(get_api_settings),
) -> SystemStatusResponse:
    auth_configured = bool(
        settings.resolved_supabase_url()
        or (settings.auth_jwt_mode == "hs256" and settings.supabase_jwt_secret)
    )
    return SystemStatusResponse(
        service=settings.app_name,
        version=settings.app_version,
        app_env=settings.app_env,
        api_bind_host=settings.api_host,
        read_only_api=True,
        trading_http_endpoints_enabled=False,
        authentication_required_for_private_data=True,
        private_data_routes_enabled=False,
        supabase_auth_configured=auth_configured,
        private_catalog_reads_enabled=settings.private_data_reads_enabled,
        database_configured=settings.database_configured,
        database_ssl_enforced_for_remote=settings.database_ssl_require,
        bybit_env=bybit_env_label_safe(),
        agent_dry_run_default=agent_dry_run_default(),
        agent_allow_live_default=agent_allow_live_default(),
        cors_origins_configured=len(settings.cors_origins),
    )
