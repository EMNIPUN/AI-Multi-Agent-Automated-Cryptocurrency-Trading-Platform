"""Authenticated principal — never trust client-supplied identity headers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Verified Supabase Auth user identity (non-secret claims only)."""

    user_id: str
    role: str
    email: str | None = None
    session_id: str | None = None
    audience: str | None = None
    issuer: str | None = None
    # Server-derived scopes only — never admin from editable user_metadata alone.
    scopes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_authenticated_user(self) -> bool:
        return self.role == "authenticated" and bool(self.user_id)
