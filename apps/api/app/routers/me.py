"""Authenticated self identity — verified JWT claims only (no secrets)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.deps import get_current_principal
from apps.api.app.schemas import MeResponse

router = APIRouter(prefix="/api/v1", tags=["me"])


@router.get("/me", response_model=MeResponse)
def read_me(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: ApiSettings = Depends(get_api_settings),
) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id,
        role=principal.role,
        email=principal.email,
        scopes=list(principal.scopes),
        private_data_reads_enabled=settings.private_data_reads_enabled,
        ownership_enforced=settings.private_data_reads_enabled,
    )
