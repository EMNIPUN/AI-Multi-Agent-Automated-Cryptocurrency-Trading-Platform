"""
JWT-bound cloud signal history APIs (owner = verified JWT sub).

Never trusts client-supplied owner_user_id. Cloud writes stay gated OFF by default.
Local SQLite history remains available on /api/v1/signals/history until cutover.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.db import configure_engine
from apps.api.app.deps import get_current_principal, require_private_catalog_access
from apps.api.app.signals.cloud_gates import gates_public_dict
from apps.api.app.signals.cloud_repository import SqlAlchemySignalCloudRepository
from apps.api.app.signals.cloud_sync import sync_health
from apps.api.app.security.db_identity import (
    attach_owner_identity,
    clear_owner_identity,
    runtime_db_identity_enabled,
)
from apps.api.app.signals.owner_binding import assert_principal_matches_bound_owner
from apps.api.app.signals.service import get_signal_store

router = APIRouter(prefix="/api/v1/signals/cloud", tags=["signals-cloud"])


def _owner_uuid(principal: AuthenticatedPrincipal) -> uuid.UUID:
    try:
        return assert_principal_matches_bound_owner(principal)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="principal_user_id_invalid_uuid") from exc


def get_cloud_repo(
    principal: AuthenticatedPrincipal = Depends(require_private_catalog_access),
    settings: ApiSettings = Depends(get_api_settings),
) -> Generator[tuple[AuthenticatedPrincipal, SqlAlchemySignalCloudRepository, Session], None, None]:
    if not settings.database_configured:
        raise HTTPException(status_code=503, detail="database_not_configured")
    configure_engine(settings)
    from apps.api.app.db import _SessionLocal

    if _SessionLocal is None:
        raise HTTPException(status_code=503, detail="database_not_configured")
    session: Session = _SessionLocal()
    owner = _owner_uuid(principal)
    # Option A: when RUNTIME_DB_IDENTITY_ENABLED, attach JWT sub as transaction-local
    # GUC. Default OFF — no remote role switch yet; app owner filters remain mandatory.
    use_guc = bool(settings.runtime_db_identity_enabled) or runtime_db_identity_enabled()
    if use_guc:
        attach_owner_identity(session, owner_user_id=owner, apply_guc=True)
    try:
        yield principal, SqlAlchemySignalCloudRepository(session, require_gates=True), session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        if use_guc:
            try:
                clear_owner_identity(session, apply_guc=True)
            except Exception:  # noqa: BLE001
                pass
        session.close()


@router.get("/status")
def cloud_persistence_status(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> dict[str, Any]:
    """Authenticated status — never invents cloud-confirmed success."""
    _ = _owner_uuid(principal)
    gates = gates_public_dict()
    health = sync_health(get_signal_store())
    return {
        **gates,
        "authenticated": True,
        "owner_from_jwt": True,
        "cloud_history_reads": "jwt_owner_scoped_when_database_configured",
        "cloud_writes_default": False,
        "local_sqlite_authority": True,
        "sync": health,
        "not_an_order": True,
        "execution_allowed": False,
        "note": (
            "Cloud history requires PRIVATE_DATA_READS_ENABLED + JWT. "
            "Writes/sync remain OFF until operator approval gates open."
        ),
    }


@router.get("/history")
def cloud_signal_history(
    ctx: Annotated[
        tuple[AuthenticatedPrincipal, SqlAlchemySignalCloudRepository, Session],
        Depends(get_cloud_repo),
    ],
    symbol: str | None = Query(default=None, max_length=32),
    category: str | None = Query(default=None, max_length=16),
    interval: str | None = Query(default=None, max_length=8),
    action: str | None = Query(default=None, max_length=16),
    strategy_version: str | None = Query(default=None, max_length=32),
    from_ms: int | None = Query(default=None, ge=0),
    to_ms: int | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> dict[str, Any]:
    principal, repo, _session = ctx
    owner = _owner_uuid(principal)
    if action and action.upper() not in {"BUY", "SELL", "HOLD", "BLOCKED"}:
        raise HTTPException(status_code=400, detail="action_invalid")
    # Reject impersonation: ignore any client owner query params by never reading them.
    items = repo.list_history(
        owner_user_id=owner,
        symbol=symbol,
        category=category,
        interval=interval,
        action=action,
        strategy_version=strategy_version,
        from_ms=from_ms,
        to_ms=to_ms,
        limit=limit,
        offset=offset,
    )
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "owner_scoped": True,
        "persistence": "supabase",
        "not_an_order": True,
        "execution_allowed": False,
        "cloud_writes": gates_public_dict(),
    }


@router.get("/history/{decision_id}")
def cloud_signal_detail(
    decision_id: str,
    ctx: Annotated[
        tuple[AuthenticatedPrincipal, SqlAlchemySignalCloudRepository, Session],
        Depends(get_cloud_repo),
    ],
) -> dict[str, Any]:
    principal, repo, _session = ctx
    owner = _owner_uuid(principal)
    if len(decision_id) > 128:
        raise HTTPException(status_code=400, detail="decision_id_invalid")
    item = repo.get_decision(owner_user_id=owner, decision_id=decision_id)
    if item is None:
        raise HTTPException(status_code=404, detail="decision_not_found")
    contribs = repo.list_contributions(owner_user_id=owner, decision_id=decision_id)
    risks = repo.list_risk_events(
        owner_user_id=owner, decision_id=decision_id, limit=20
    )
    return {
        "item": item,
        "contributions": contribs,
        "risk_events": risks,
        "owner_scoped": True,
        "not_an_order": True,
        "execution_allowed": False,
    }


@router.get("/risk")
def cloud_risk_history(
    ctx: Annotated[
        tuple[AuthenticatedPrincipal, SqlAlchemySignalCloudRepository, Session],
        Depends(get_cloud_repo),
    ],
    decision_id: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> dict[str, Any]:
    principal, repo, _session = ctx
    owner = _owner_uuid(principal)
    return {
        "items": repo.list_risk_events(
            owner_user_id=owner,
            decision_id=decision_id,
            limit=limit,
            offset=offset,
        ),
        "owner_scoped": True,
        "not_an_order": True,
        "execution_allowed": False,
    }


@router.get("/strategies")
def cloud_strategy_history(
    ctx: Annotated[
        tuple[AuthenticatedPrincipal, SqlAlchemySignalCloudRepository, Session],
        Depends(get_cloud_repo),
    ],
) -> dict[str, Any]:
    principal, repo, _session = ctx
    owner = _owner_uuid(principal)
    return {
        "items": repo.list_strategy_versions(owner_user_id=owner),
        "owner_scoped": True,
        "not_an_order": True,
        "execution_allowed": False,
    }


@router.get("/analytics")
def cloud_signal_analytics(
    ctx: Annotated[
        tuple[AuthenticatedPrincipal, SqlAlchemySignalCloudRepository, Session],
        Depends(get_cloud_repo),
    ],
) -> dict[str, Any]:
    principal, repo, _session = ctx
    owner = _owner_uuid(principal)
    data = repo.analytics(owner_user_id=owner)
    data["not_an_order"] = True
    data["execution_allowed"] = False
    data["owner_scoped"] = True
    return data


@router.get("/sync/health")
def cloud_sync_health_authed(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
) -> dict[str, Any]:
    _ = _owner_uuid(principal)
    return sync_health(get_signal_store())
