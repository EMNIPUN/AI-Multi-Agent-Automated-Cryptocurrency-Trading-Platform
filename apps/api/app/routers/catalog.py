"""
Protected catalog reads (Phase 2D).

Require verified Supabase user JWT + PRIVATE_DATA_READS_ENABLED + owner filter.
No mutation or trading routes.
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.catalog_service import (
    CatalogReadContext,
    list_agent_decisions,
    list_strategies,
    list_system_events,
)
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.db import configure_engine
from apps.api.app.deps import require_private_catalog_access
from apps.api.app.schemas import (
    AgentDecisionListResponse,
    PaginationQuery,
    StrategyConfigListResponse,
    SystemEventListResponse,
)

router = APIRouter(prefix="/api/v1", tags=["catalog"])


def _pagination(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
) -> PaginationQuery:
    return PaginationQuery(limit=limit, offset=offset)


def get_catalog_read_context(
    page: PaginationQuery = Depends(_pagination),
    principal: AuthenticatedPrincipal = Depends(require_private_catalog_access),
    settings: ApiSettings = Depends(get_api_settings),
) -> Generator[CatalogReadContext, None, None]:
    """
    Open a DB session only after auth + ownership gate + pagination validation.

    Per-request session; never SET ROLE / request GUCs (avoids pool bleed).
    Application filters by principal.user_id — do not trust client user ids.
    """
    if not settings.database_configured:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="database_not_configured")
    configure_engine(settings)
    from apps.api.app.db import _SessionLocal

    if _SessionLocal is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="database_not_configured")

    session: Session = _SessionLocal()
    try:
        yield CatalogReadContext(page=page, principal=principal, session=session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@router.get("/agents/decisions", response_model=AgentDecisionListResponse)
def get_agent_decisions(
    ctx: CatalogReadContext = Depends(get_catalog_read_context),
) -> AgentDecisionListResponse:
    return list_agent_decisions(ctx)


@router.get("/system/events", response_model=SystemEventListResponse)
def get_system_events(
    ctx: CatalogReadContext = Depends(get_catalog_read_context),
) -> SystemEventListResponse:
    return list_system_events(ctx)


@router.get("/strategies", response_model=StrategyConfigListResponse)
def get_strategies(
    ctx: CatalogReadContext = Depends(get_catalog_read_context),
) -> StrategyConfigListResponse:
    return list_strategies(ctx)
