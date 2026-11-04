"""Auth errors — messages never include tokens or secrets."""

from __future__ import annotations


class AuthError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AuthConfigError(AuthError):
    """Fail closed when verifier cannot be configured or JWKS unavailable."""
