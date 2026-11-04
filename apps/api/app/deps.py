"""FastAPI dependencies — auth fail-closed; DB sessions isolated per request."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from apps.api.app.auth.errors import AuthConfigError, AuthError
from apps.api.app.auth.jwt_verifier import (
    TokenVerifier,
    build_token_verifier_from_settings,
)
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.db import configure_engine
from apps.api.app.ownership import assert_private_data_reads_allowed

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _cached_verifier_fingerprint(fingerprint: str) -> TokenVerifier:
    # fingerprint forces rebuild when settings change in tests via cache_clear.
    settings = get_api_settings()
    return build_token_verifier_from_settings(settings)


def clear_verifier_cache() -> None:
    _cached_verifier_fingerprint.cache_clear()


def get_token_verifier(
    request: Request,
    settings: ApiSettings = Depends(get_api_settings),
) -> TokenVerifier:
    """Prefer app.state override (tests); else build from settings."""
    override = getattr(request.app.state, "token_verifier", None)
    if override is not None:
        return override  # type: ignore[no-any-return]
    try:
        fp = (
            f"{settings.auth_jwt_mode}|{settings.resolved_jwt_issuer()}|"
            f"{settings.resolved_jwks_url()}|{bool(settings.supabase_jwt_secret)}"
        )
        return _cached_verifier_fingerprint(fp)
    except AuthConfigError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="auth_verifier_unavailable") from exc


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: ApiSettings = Depends(get_api_settings),
) -> AuthenticatedPrincipal:
    # Check credentials before constructing verifier (avoid 503 on missing Bearer).
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="missing_authorization")
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="invalid_authorization_scheme")
    token = credentials.credentials.strip()
    verifier = get_token_verifier(request, settings)
    try:
        principal = verifier.verify_access_token(token)
    except AuthConfigError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=exc.code) from exc
    if not principal.is_authenticated_user:
        raise HTTPException(status_code=401, detail="non_user_token")
    return principal


def require_private_catalog_access(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: ApiSettings = Depends(get_api_settings),
) -> AuthenticatedPrincipal:
    """Auth required + PRIVATE_DATA_READS_ENABLED gate (default deny)."""
    assert_private_data_reads_allowed(settings, principal)
    return principal


def settings_dep() -> ApiSettings:
    return get_api_settings()


def get_db_session() -> Generator[Session, None, None]:
    """
    Per-request SQLAlchemy session.

    Does not SET ROLE or request-scoped GUCs — avoids leaking ownership context
    across pooled connections. Catalog routes open sessions via
    ``get_catalog_read_context`` after the ownership gate.
    """
    settings = get_api_settings()
    if not settings.database_configured:
        raise HTTPException(
            status_code=503,
            detail="database_not_configured",
        )
    configure_engine(settings)
    from apps.api.app.db import _SessionLocal

    if _SessionLocal is None:
        raise HTTPException(status_code=503, detail="database_not_configured")
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
