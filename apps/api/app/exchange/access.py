"""Access mode selection for exchange/telemetry reads (Phase 3C)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum

from fastapi import HTTPException, Request
from fastapi.security.utils import get_authorization_scheme_param

from apps.api.app.auth.jwt_verifier import TokenVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings
from apps.api.app.exchange.binding_store import InMemoryBindingStore
from apps.api.app.exchange.bindings import (
    BindingStore,
    ExchangeAccountBinding,
    ExchangeEnvironment,
    require_active_binding_for_principal,
)
from apps.api.app.security.operator_local import assert_operator_local_diagnostic


class ExchangeReadMode(str, Enum):
    OPERATOR_LOCAL = "operator_local"
    OWNER_BOUND = "owner_bound"


@dataclass(frozen=True, slots=True)
class ExchangeReadContext:
    mode: ExchangeReadMode
    principal: AuthenticatedPrincipal | None = None
    binding: ExchangeAccountBinding | None = None


def get_binding_store(request: Request, settings: ApiSettings | None = None) -> BindingStore:
    """
    Prefer test/app override. Else SQLAlchemy store when DATABASE_URL is set.
    Else empty in-memory store (owner-bound paths still require PRIVATE_DATA_READS
    + real bindings — never invent ownership).
    """
    override = getattr(request.app.state, "exchange_binding_store", None)
    if override is not None:
        return override  # type: ignore[no-any-return]

    settings = settings or getattr(request.app.state, "settings", None)
    if settings is not None and getattr(settings, "database_configured", False):
        from apps.api.app.db import configure_engine
        from apps.api.app.exchange.binding_store import SqlAlchemyBindingStore
        from apps.api.app.db import _SessionLocal

        configure_engine(settings)
        if _SessionLocal is not None:
            store = SqlAlchemyBindingStore.from_sessionmaker(_SessionLocal)
            request.app.state.exchange_binding_store = store
            return store

    store = InMemoryBindingStore()
    request.app.state.exchange_binding_store = store
    return store


def _optional_bearer_principal(
    request: Request, settings: ApiSettings
) -> AuthenticatedPrincipal | None:
    auth = request.headers.get("authorization")
    if not auth:
        return None
    scheme, token = get_authorization_scheme_param(auth)
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="invalid_authorization_scheme")
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        from apps.api.app.deps import get_token_verifier

        verifier = get_token_verifier(request, settings)
    from apps.api.app.auth.errors import AuthConfigError, AuthError

    try:
        principal = verifier.verify_access_token(token)
    except AuthConfigError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=exc.code) from exc
    if not principal.is_authenticated_user:
        raise HTTPException(status_code=401, detail="non_user_token")
    return principal


def resolve_exchange_read_context(
    request: Request,
    settings: ApiSettings,
    *,
    environment: ExchangeEnvironment | None = None,
    binding_id: uuid.UUID | None = None,
) -> ExchangeReadContext:
    """
    Dual-path authorization:

    1) Operator-local diagnostic (no Authorization) — loopback TCP peer only.
    2) Owner-bound authenticated read — requires active binding + PRIVATE_DATA_READS.

    Presence of Authorization never falls through to operator-local.
    """
    principal = _optional_bearer_principal(request, settings)
    if principal is not None:
        store = get_binding_store(request, settings)
        binding = require_active_binding_for_principal(
            principal=principal,
            store=store,
            settings=settings,
            environment=environment,
            requested_binding_id=binding_id,
        )
        return ExchangeReadContext(
            mode=ExchangeReadMode.OWNER_BOUND,
            principal=principal,
            binding=binding,
        )

    assert_operator_local_diagnostic(request, settings)
    return ExchangeReadContext(mode=ExchangeReadMode.OPERATOR_LOCAL)
