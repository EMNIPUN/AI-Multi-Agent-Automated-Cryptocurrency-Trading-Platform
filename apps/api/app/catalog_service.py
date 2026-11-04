"""
Owner-scoped catalog reads (Phase 2D).

Application authorization is primary: every query filters by principal.user_id.
RLS is defense in depth and may be bypassed by postgres/table-owner connections.
Never invent ownership for NULL owner_user_id rows — equality excludes them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.models import AgentDecision, StrategyConfig, SystemEvent
from apps.api.app.sanitize import sanitize_public_json
from apps.api.app.schemas import (
    AgentDecisionItem,
    AgentDecisionListResponse,
    PaginationQuery,
    StrategyConfigItem,
    StrategyConfigListResponse,
    SystemEventItem,
    SystemEventListResponse,
)

# Event types that must never leave the API (credentials / raw account material).
_BLOCKED_SYSTEM_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "credential_material",
        "secret_rotation",
        "api_key_event",
        "raw_account_dump",
        "exchange_credential",
    }
)


def parse_owner_uuid(principal: AuthenticatedPrincipal) -> uuid.UUID:
    """JWT sub must be a UUID for app.owner_user_id equality filters."""
    try:
        return uuid.UUID(str(principal.user_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(status_code=403, detail="invalid_owner_identity") from exc


def _fail_closed_query(exc: BaseException) -> HTTPException:
    """Map DB errors to safe client responses (no row leakage, no SQL text)."""
    text = str(exc).lower()
    # Missing column / relation → schema not migrated (or wrong DB).
    if isinstance(exc, ProgrammingError) or any(
        token in text
        for token in (
            "owner_user_id",
            "undefined column",
            "does not exist",
            "no such table",
            "no such column",
            "undefinedtable",
            "undefinedcolumn",
        )
    ):
        return HTTPException(status_code=503, detail="ownership_schema_unavailable")
    return HTTPException(status_code=503, detail="catalog_query_failed")


@dataclass(frozen=True, slots=True)
class CatalogReadContext:
    page: PaginationQuery
    principal: AuthenticatedPrincipal
    session: Session


def list_agent_decisions(
    ctx: CatalogReadContext,
) -> AgentDecisionListResponse:
    owner = parse_owner_uuid(ctx.principal)
    try:
        stmt = (
            select(AgentDecision)
            .where(AgentDecision.owner_user_id == owner)
            .order_by(AgentDecision.created_at.desc(), AgentDecision.id.desc())
            .offset(ctx.page.offset)
            .limit(ctx.page.limit)
        )
        rows = list(ctx.session.scalars(stmt).all())
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — fail closed on any query failure
        raise _fail_closed_query(exc) from exc

    items = [
        AgentDecisionItem(
            id=str(row.id),
            created_at=row.created_at if isinstance(row.created_at, datetime) else row.created_at,
            env_scope=row.env_scope,
            symbol=row.symbol,
            category=row.category,
            action=row.action,
            strategy_id=row.strategy_id,
            signal_id=row.signal_id,
            correlation_id=row.correlation_id,
            reason=row.reason,
            payload_json=sanitize_public_json(row.payload_json),
        )
        for row in rows
    ]
    return AgentDecisionListResponse(
        items=items, limit=ctx.page.limit, offset=ctx.page.offset
    )


def list_system_events(ctx: CatalogReadContext) -> SystemEventListResponse:
    owner = parse_owner_uuid(ctx.principal)
    try:
        stmt = (
            select(SystemEvent)
            .where(SystemEvent.owner_user_id == owner)
            .where(SystemEvent.event_type.notin_(sorted(_BLOCKED_SYSTEM_EVENT_TYPES)))
            .order_by(SystemEvent.created_at.desc(), SystemEvent.id.desc())
            .offset(ctx.page.offset)
            .limit(ctx.page.limit)
        )
        rows = list(ctx.session.scalars(stmt).all())
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _fail_closed_query(exc) from exc

    items: list[SystemEventItem] = []
    for row in rows:
        if row.event_type in _BLOCKED_SYSTEM_EVENT_TYPES:
            continue
        items.append(
            SystemEventItem(
                id=str(row.id),
                created_at=row.created_at,
                env_scope=row.env_scope,
                severity=row.severity,
                event_type=row.event_type,
                message=row.message[:2_000] if row.message else "",
                details_json=sanitize_public_json(row.details_json),
            )
        )
    return SystemEventListResponse(
        items=items, limit=ctx.page.limit, offset=ctx.page.offset
    )


def list_strategies(ctx: CatalogReadContext) -> StrategyConfigListResponse:
    owner = parse_owner_uuid(ctx.principal)
    try:
        stmt = (
            select(StrategyConfig)
            .where(StrategyConfig.owner_user_id == owner)
            .order_by(StrategyConfig.created_at.desc(), StrategyConfig.id.desc())
            .offset(ctx.page.offset)
            .limit(ctx.page.limit)
        )
        rows = list(ctx.session.scalars(stmt).all())
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _fail_closed_query(exc) from exc

    items = [
        StrategyConfigItem(
            id=str(row.id),
            created_at=row.created_at,
            updated_at=row.updated_at,
            name=row.name,
            version=row.version,
            enabled=row.enabled,
            config_json=sanitize_public_json(row.config_json),
        )
        for row in rows
    ]
    return StrategyConfigListResponse(
        items=items, limit=ctx.page.limit, offset=ctx.page.offset
    )
