"""Paper read API dependencies — feature gate + loopback diagnostic access."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from agent.paper.read_store import PaperDbUnavailable, PaperReadStore
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.paper.schemas import PaperDisabledResponse
from apps.api.app.paper.service import resolve_paper_db_path
from apps.api.app.security.operator_local import assert_operator_local_diagnostic


def require_paper_read_enabled(
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> ApiSettings:
    if not settings.paper_read_api_enabled:
        raise HTTPException(
            status_code=503,
            detail=PaperDisabledResponse().model_dump(),
        )
    return settings


def require_paper_local_access(
    request: Request,
    settings: Annotated[ApiSettings, Depends(require_paper_read_enabled)],
) -> ApiSettings:
    """
    Paper journal is local-operator diagnostic data (not multi-tenant cloud).

    Reuse loopback diagnostic gate — no JWT private-data expansion, no CORS weaken.
    """
    assert_operator_local_diagnostic(request, settings)
    return settings


def get_paper_read_store(
    settings: Annotated[ApiSettings, Depends(require_paper_local_access)],
) -> PaperReadStore:
    path = resolve_paper_db_path(settings.paper_sqlite_path)
    store = PaperReadStore(path)
    if not store.exists():
        # Empty: allow status/list to return empty without creating the file.
        return store
    try:
        # Probe readability without writes.
        _ = store.schema_version()
    except PaperDbUnavailable as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "detail": "paper_db_error",
                "message": "Paper database unreadable or corrupt",
                "code": str(exc),
            },
        ) from exc
    return store


def paper_db_path(
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> Path:
    return resolve_paper_db_path(settings.paper_sqlite_path)
