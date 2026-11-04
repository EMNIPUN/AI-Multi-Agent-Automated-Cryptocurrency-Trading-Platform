"""
Supabase Auth access-token verification.

Modes:
- jwks (default): asymmetric keys from project JWKS; algorithms ES256/RS256 only.
- hs256 (legacy): server-side JWT secret only — never ship secret to browsers.

Fail closed on JWKS/network/config failures. Never log raw tokens.
"""

from __future__ import annotations

from typing import Any, Protocol

import jwt
from jwt import PyJWKClient

from apps.api.app.auth.errors import AuthConfigError, AuthError
from apps.api.app.auth.principal import AuthenticatedPrincipal

# Explicit allowlists — never "accept any".
_JWKS_ALGORITHMS = ("ES256", "RS256")
_HS256_ALGORITHMS = ("HS256",)
_ALLOWED_USER_ROLES = frozenset({"authenticated"})
_REJECTED_ROLES = frozenset({"anon", "service_role"})


class TokenVerifier(Protocol):
    def verify_access_token(self, token: str) -> AuthenticatedPrincipal: ...


def _require_claim(payload: dict[str, Any], key: str) -> Any:
    if key not in payload or payload[key] in (None, ""):
        raise AuthError(f"missing_claim_{key}")
    return payload[key]


def principal_from_payload(payload: dict[str, Any]) -> AuthenticatedPrincipal:
    role = str(_require_claim(payload, "role"))
    if role in _REJECTED_ROLES:
        raise AuthError("non_user_token")
    if role not in _ALLOWED_USER_ROLES:
        raise AuthError("unsupported_role")
    sub = str(_require_claim(payload, "sub"))
    email = payload.get("email")
    session_id = payload.get("session_id")
    aud = payload.get("aud")
    if isinstance(aud, list):
        aud_s = ",".join(str(a) for a in aud)
    else:
        aud_s = str(aud) if aud is not None else None
    return AuthenticatedPrincipal(
        user_id=sub,
        role=role,
        email=str(email) if email else None,
        session_id=str(session_id) if session_id else None,
        audience=aud_s,
        issuer=str(payload["iss"]) if payload.get("iss") else None,
        scopes=("read:self",),
    )


class SupabaseJWKSVerifier:
    """Verify user access JWTs via Supabase JWKS (preferred)."""

    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
        leeway_seconds: int = 30,
        jwks_client: PyJWKClient | None = None,
    ) -> None:
        if not jwks_url.strip() or not issuer.strip() or not audience.strip():
            raise AuthConfigError("jwks_verifier_misconfigured")
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._leeway = leeway_seconds
        self._jwks = jwks_client or PyJWKClient(jwks_url, cache_keys=True)

    def verify_access_token(self, token: str) -> AuthenticatedPrincipal:
        if not token or token.count(".") != 2:
            raise AuthError("malformed_token")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError as exc:
            raise AuthError("malformed_token") from exc
        alg = header.get("alg")
        if alg not in _JWKS_ALGORITHMS:
            raise AuthError("unsupported_algorithm")
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
        except Exception as exc:  # noqa: BLE001 — network/JWKS/key miss → fail closed
            raise AuthConfigError("jwks_unavailable") from exc
        try:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(_JWKS_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": ["exp", "sub", "iss", "aud"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
                leeway=self._leeway,
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("token_expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise AuthError("invalid_audience") from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthError("invalid_issuer") from exc
        except jwt.ImmatureSignatureError as exc:
            raise AuthError("token_not_yet_valid") from exc
        except jwt.InvalidSignatureError as exc:
            raise AuthError("invalid_signature") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError("invalid_token") from exc
        if not isinstance(payload, dict):
            raise AuthError("invalid_token")
        return principal_from_payload(payload)


class SupabaseHS256Verifier:
    """
    Legacy symmetric verification using the project's JWT secret (server-side only).

    Prefer JWKS/ES256 when the project uses asymmetric signing.
    """

    def __init__(
        self,
        *,
        secret: str,
        issuer: str,
        audience: str,
        leeway_seconds: int = 30,
    ) -> None:
        if not secret or not issuer.strip() or not audience.strip():
            raise AuthConfigError("hs256_verifier_misconfigured")
        self._secret = secret
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._leeway = leeway_seconds

    def verify_access_token(self, token: str) -> AuthenticatedPrincipal:
        if not token or token.count(".") != 2:
            raise AuthError("malformed_token")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError as exc:
            raise AuthError("malformed_token") from exc
        if header.get("alg") != "HS256":
            raise AuthError("unsupported_algorithm")
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=list(_HS256_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": ["exp", "sub", "iss", "aud"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
                leeway=self._leeway,
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("token_expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise AuthError("invalid_audience") from exc
        except jwt.InvalidIssuerError as exc:
            raise AuthError("invalid_issuer") from exc
        except jwt.ImmatureSignatureError as exc:
            raise AuthError("token_not_yet_valid") from exc
        except jwt.InvalidSignatureError as exc:
            raise AuthError("invalid_signature") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError("invalid_token") from exc
        if not isinstance(payload, dict):
            raise AuthError("invalid_token")
        return principal_from_payload(payload)


class StaticMappingVerifier:
    """Deterministic offline test double — maps token strings to principals or errors."""

    def __init__(
        self,
        mapping: dict[str, AuthenticatedPrincipal | AuthError | AuthConfigError],
    ) -> None:
        self._mapping = mapping

    def verify_access_token(self, token: str) -> AuthenticatedPrincipal:
        if token not in self._mapping:
            raise AuthError("invalid_token")
        value = self._mapping[token]
        if isinstance(value, AuthError):
            raise value
        return value


def build_token_verifier_from_settings(settings: Any) -> TokenVerifier:
    """Factory used by FastAPI deps — fail closed if auth is incomplete."""
    mode = str(getattr(settings, "auth_jwt_mode", "jwks") or "jwks").strip().lower()
    issuer_fn = getattr(settings, "resolved_jwt_issuer", None)
    issuer = issuer_fn() if callable(issuer_fn) else (getattr(settings, "supabase_jwt_issuer", "") or "")
    audience = getattr(settings, "supabase_jwt_audience", "authenticated") or "authenticated"
    if mode == "jwks":
        jwks_fn = getattr(settings, "resolved_jwks_url", None)
        jwks_url = (
            jwks_fn() if callable(jwks_fn) else (getattr(settings, "supabase_jwks_url", "") or "")
        )
        if not jwks_url or not issuer:
            raise AuthConfigError("jwks_url_missing")
        return SupabaseJWKSVerifier(
            jwks_url=jwks_url,
            issuer=issuer,
            audience=audience,
            leeway_seconds=int(getattr(settings, "auth_jwt_leeway_seconds", 30)),
        )
    if mode == "hs256":
        secret = getattr(settings, "supabase_jwt_secret", None) or ""
        if not issuer:
            raise AuthConfigError("hs256_verifier_misconfigured")
        return SupabaseHS256Verifier(
            secret=secret,
            issuer=issuer,
            audience=audience,
            leeway_seconds=int(getattr(settings, "auth_jwt_leeway_seconds", 30)),
        )
    raise AuthConfigError("unsupported_auth_jwt_mode")
