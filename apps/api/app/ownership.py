"""
Ownership / tenant isolation (Phase 2D).

- owner_user_id (UUID) = verified Supabase Auth JWT ``sub``.
- env_scope / account_fp alone never prove ownership.
- NULL owner_user_id rows stay inaccessible to ordinary users.
- RLS is defense in depth; FastAPI owner filters are mandatory even if the DB
  role bypasses RLS (postgres / table owner / service_role).
- Future: organization_id / team membership and exchange_account ownership will
  layer on top of user ownership (not implemented in Phase 2D).
"""

from __future__ import annotations

from fastapi import HTTPException

from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings


def assert_private_data_reads_allowed(
    settings: ApiSettings,
    principal: AuthenticatedPrincipal,
) -> None:
    """Deny-by-default until operator enables PRIVATE_DATA_READS_ENABLED."""
    if not principal.is_authenticated_user:
        raise HTTPException(status_code=403, detail="forbidden")
    if not settings.private_data_reads_enabled:
        raise HTTPException(
            status_code=403,
            detail="ownership_schema_required",
        )


def assert_same_user(principal: AuthenticatedPrincipal, resource_user_id: str) -> None:
    if principal.user_id != resource_user_id:
        raise HTTPException(status_code=403, detail="cross_tenant_forbidden")


def assert_owner_matches(
    principal: AuthenticatedPrincipal, row_owner_user_id: str | None
) -> None:
    """Row-level check for future single-resource routes (fail closed on NULL)."""
    if row_owner_user_id is None or row_owner_user_id == "":
        raise HTTPException(status_code=403, detail="unowned_resource")
    if principal.user_id != str(row_owner_user_id):
        raise HTTPException(status_code=403, detail="cross_tenant_forbidden")
