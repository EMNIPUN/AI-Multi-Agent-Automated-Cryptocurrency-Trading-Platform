"""Bybit Testnet credential verification adapter (Part 6D).

Deterministic / injectable clients only. Never opens real network sockets.
Never places orders or requests withdrawals. Never activates bindings.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from apps.api.app.exchange.bindings import ExchangeEnvironment
from apps.api.app.exchange.credential_registry import (
    CredentialPermissionClass,
    CredentialRecord,
    CredentialRegistry,
    CredentialVerificationState,
    assert_user_cannot_claim_operator_ref,
    redact_secret_material,
)
from apps.api.app.exchange.credential_verification import (
    VerificationDenyReason,
    VerificationGates,
    VerificationOutcome,
    activation_allowed_after_verification,
)

_log = logging.getLogger("cryptonova.bybit_testnet_adapter")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AdapterErrorCode(str, Enum):
    INVALID_CREDENTIALS = "invalid_credentials"
    WRONG_ENVIRONMENT = "wrong_environment"
    NETWORK_TIMEOUT = "network_timeout"
    RATE_LIMITED = "rate_limited"
    MALFORMED_RESPONSE = "malformed_exchange_response"
    OWNERSHIP_MISMATCH = "credential_ownership_mismatch"
    PERMISSION_MISMATCH = "permission_mismatch"
    REVOKED = "credential_already_revoked"
    UNEXPECTED = "unexpected_adapter_exception"
    MAINNET_FORBIDDEN = "mainnet_verification_forbidden"
    CREDENTIAL_NOT_FOUND = "credential_not_found"
    GATES_BLOCKED = "verification_gates_blocked"


class BybitTestnetReadClient(Protocol):
    """Read-only Testnet client — implementations must not trade."""

    def fetch_account_identity(self) -> dict[str, Any]:
        """Return a Bybit-shaped dict (retCode/retMsg/result). No secrets."""
        ...


@dataclass(frozen=True, slots=True)
class FakeBybitScenario:
    """Deterministic fake exchange behavior for tests."""

    mode: str = "ok"  # ok|invalid|timeout|rate_limit|malformed|wrong_env|exception
    uid: str = "testnet-uid-1001"
    account_type: str = "UNIFIED"
    environment_label: str = "testnet"


class FakeBybitTestnetClient:
    """Injected fake — never performs network I/O."""

    def __init__(self, scenario: FakeBybitScenario | None = None) -> None:
        self.scenario = scenario or FakeBybitScenario()
        self.call_count = 0

    def fetch_account_identity(self) -> dict[str, Any]:
        self.call_count += 1
        mode = self.scenario.mode
        if mode == "timeout":
            raise TimeoutError("bybit_testnet_timeout")
        if mode == "exception":
            raise RuntimeError("unexpected_fake_failure")
        if mode == "rate_limit":
            return {"retCode": 10006, "retMsg": "Too many visits!", "result": {}}
        if mode == "invalid":
            return {"retCode": 10003, "retMsg": "Invalid API key", "result": {}}
        if mode == "malformed":
            return {"retCode": 0, "retMsg": "OK", "result": "not-a-dict"}
        if mode == "wrong_env":
            return {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "uid": self.scenario.uid,
                    "accountType": self.scenario.account_type,
                    "environment": "mainnet",
                },
            }
        return {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "uid": self.scenario.uid,
                "accountType": self.scenario.account_type,
                "environment": self.scenario.environment_label,
            },
        }


@dataclass(frozen=True, slots=True)
class AdapterVerificationResult:
    ok: bool
    reason: str | None
    exchange_account_fingerprint: str | None
    permission_class: str | None
    environment: str | None
    simulated: bool
    audited_at: datetime | None
    audit_event: str | None
    activates_binding: bool = False
    enables_private_reads: bool = False
    safe_message: str = ""

    def to_public_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "exchange_account_fingerprint": self.exchange_account_fingerprint,
            "permission_class": self.permission_class,
            "environment": self.environment,
            "simulated": self.simulated,
            "audited_at": self.audited_at.isoformat() if self.audited_at else None,
            "audit_event": self.audit_event,
            "activates_binding": False,
            "enables_private_reads": False,
            "safe_message": self.safe_message,
            "is_live_bybit_connection": False,
        }


def _fingerprint(uid: str, account_type: str) -> str:
    digest = hashlib.sha256(f"{uid}:{account_type}:testnet".encode()).hexdigest()[:16]
    return f"bybit-testnet:{digest}"


def _safe_log(event: str, **fields: object) -> None:
    """Log only non-secret structured fields."""
    cleaned = {k: redact_secret_material(str(v)) for k, v in fields.items()}
    _log.info("event=%s %s", event, cleaned)


_DEDUP_LOCK = threading.Lock()
_IN_FLIGHT: set[str] = set()


class BybitTestnetVerificationAdapter:
    """
    Orchestrates ownership checks + injected read client.

    Live network clients are intentionally unsupported in Part 6D.
    """

    def __init__(
        self,
        *,
        registry: CredentialRegistry,
        client: BybitTestnetReadClient,
        simulated: bool = True,
    ) -> None:
        self._registry = registry
        self._client = client
        self._simulated = simulated

    def verify_readonly(
        self,
        *,
        credential_id: uuid.UUID,
        actor_owner_user_id: uuid.UUID,
        gates: VerificationGates | None = None,
        update_registry: bool = True,
    ) -> AdapterVerificationResult:
        gates = gates or VerificationGates()
        dedupe_key = f"{credential_id}:{actor_owner_user_id}"
        with _DEDUP_LOCK:
            if dedupe_key in _IN_FLIGHT:
                return AdapterVerificationResult(
                    ok=False,
                    reason="duplicate_verification_in_flight",
                    exchange_account_fingerprint=None,
                    permission_class=None,
                    environment=None,
                    simulated=self._simulated,
                    audited_at=_utc_now(),
                    audit_event="bybit_testnet_verify_duplicate",
                    safe_message="A verification request is already in progress.",
                )
            _IN_FLIGHT.add(dedupe_key)

        try:
            return self._verify_inner(
                credential_id=credential_id,
                actor_owner_user_id=actor_owner_user_id,
                gates=gates,
                update_registry=update_registry,
            )
        finally:
            with _DEDUP_LOCK:
                _IN_FLIGHT.discard(dedupe_key)

    def _verify_inner(
        self,
        *,
        credential_id: uuid.UUID,
        actor_owner_user_id: uuid.UUID,
        gates: VerificationGates,
        update_registry: bool,
    ) -> AdapterVerificationResult:
        record = self._registry.get(credential_id)
        if record is None:
            return self._fail(
                AdapterErrorCode.CREDENTIAL_NOT_FOUND,
                "Credential was not found.",
            )
        try:
            assert_user_cannot_claim_operator_ref(record.public_ref)
        except ValueError:
            return self._fail(
                AdapterErrorCode.OWNERSHIP_MISMATCH,
                "Operator credentials cannot be claimed for user verification.",
            )
        if record.revoked_at is not None or (
            record.verification_state is CredentialVerificationState.REVOKED
        ):
            return self._fail(AdapterErrorCode.REVOKED, "Credential is revoked.")
        if record.owner_user_id != actor_owner_user_id:
            return self._fail(
                AdapterErrorCode.OWNERSHIP_MISMATCH,
                "Credential does not belong to the authenticated user.",
            )
        if record.environment is not ExchangeEnvironment.TESTNET:
            return self._fail(
                AdapterErrorCode.MAINNET_FORBIDDEN
                if record.environment is ExchangeEnvironment.MAINNET
                else AdapterErrorCode.WRONG_ENVIRONMENT,
                "Only Bybit Testnet verification is supported.",
            )
        if record.permission_class is not CredentialPermissionClass.READ_ONLY:
            return self._fail(
                AdapterErrorCode.PERMISSION_MISMATCH,
                "Only read-only credentials can be verified.",
            )

        # Part 6D simulator may run without live external-call gates when simulated=True.
        # Live path (simulated=False) still requires full VerificationGates.
        if not self._simulated:
            if not gates.operator_approved or not gates.allow_external_bybit_calls:
                return self._fail(
                    AdapterErrorCode.GATES_BLOCKED,
                    "External Bybit verification is not approved.",
                )

        try:
            raw = self._client.fetch_account_identity()
        except TimeoutError:
            _safe_log("bybit_testnet_timeout", credential_id=str(credential_id))
            return self._fail(
                AdapterErrorCode.NETWORK_TIMEOUT,
                "Verification timed out contacting the exchange simulator.",
            )
        except Exception as exc:  # noqa: BLE001 — fail closed; no secret detail
            _safe_log(
                "bybit_testnet_unexpected",
                credential_id=str(credential_id),
                error_type=type(exc).__name__,
            )
            return self._fail(
                AdapterErrorCode.UNEXPECTED,
                "Verification failed due to an unexpected adapter error.",
            )

        parsed = self._validate_response(raw)
        if isinstance(parsed, AdapterVerificationResult):
            return parsed

        uid, account_type, env_label = parsed
        if env_label != "testnet":
            return self._fail(
                AdapterErrorCode.WRONG_ENVIRONMENT,
                "Exchange response was not Testnet.",
            )

        fingerprint = _fingerprint(uid, account_type)
        now = _utc_now()
        if update_registry:
            verified = CredentialRecord(
                id=record.id,
                owner_user_id=record.owner_user_id,
                provider=record.provider,
                environment=record.environment,
                public_ref=record.public_ref,
                secret_storage_ref=record.secret_storage_ref,
                permission_class=record.permission_class,
                verification_state=CredentialVerificationState.VERIFIED,
                operator_managed=record.operator_managed,
                created_at=record.created_at,
                rotated_at=record.rotated_at,
                revoked_at=record.revoked_at,
                last_verified_at=now,
                exchange_account_fingerprint=fingerprint,
            )
            self._registry.upsert(verified)

        outcome = VerificationOutcome(
            ok=True,
            reason=None,
            exchange_account_fingerprint=fingerprint,
            audited_at=now,
            audit_event="bybit_testnet_verification_simulated_ok"
            if self._simulated
            else "bybit_testnet_verification_ok",
        )
        # Never activate bindings or enable private reads from this adapter.
        allowed, _reason = activation_allowed_after_verification(
            verification=outcome, gates=gates
        )
        assert allowed is False

        _safe_log(
            "bybit_testnet_verify_ok",
            credential_id=str(credential_id),
            fingerprint=fingerprint,
            simulated=self._simulated,
        )
        return AdapterVerificationResult(
            ok=True,
            reason=None,
            exchange_account_fingerprint=fingerprint,
            permission_class=CredentialPermissionClass.READ_ONLY.value,
            environment=ExchangeEnvironment.TESTNET.value,
            simulated=self._simulated,
            audited_at=now,
            audit_event=outcome.audit_event,
            activates_binding=False,
            enables_private_reads=False,
            safe_message=(
                "Simulated Testnet verification succeeded. "
                "This is not a live Bybit connection and does not activate the binding."
                if self._simulated
                else "Testnet verification succeeded (binding not activated)."
            ),
        )

    def _validate_response(
        self, raw: dict[str, Any]
    ) -> tuple[str, str, str] | AdapterVerificationResult:
        if not isinstance(raw, dict):
            return self._fail(
                AdapterErrorCode.MALFORMED_RESPONSE,
                "Exchange response was malformed.",
            )
        ret = raw.get("retCode")
        if ret == 10006:
            return self._fail(
                AdapterErrorCode.RATE_LIMITED,
                "Exchange rate limit exceeded (simulator).",
            )
        if ret in {10003, 10004, 10005}:
            return self._fail(
                AdapterErrorCode.INVALID_CREDENTIALS,
                "Credentials were rejected by the exchange simulator.",
            )
        if ret != 0:
            return self._fail(
                AdapterErrorCode.INVALID_CREDENTIALS,
                "Exchange simulator rejected the verification request.",
            )
        result = raw.get("result")
        if not isinstance(result, dict):
            return self._fail(
                AdapterErrorCode.MALFORMED_RESPONSE,
                "Exchange response was malformed.",
            )
        uid = str(result.get("uid") or "").strip()
        account_type = str(result.get("accountType") or "").strip()
        env_label = str(result.get("environment") or "").strip().lower()
        if not uid or not account_type or not env_label:
            return self._fail(
                AdapterErrorCode.MALFORMED_RESPONSE,
                "Exchange response was missing required identity fields.",
            )
        # Reject trade/withdraw capability claims if ever present.
        perms = result.get("permissions")
        if isinstance(perms, (list, tuple)) and any(
            str(p).lower() in {"order", "trade", "withdraw"} for p in perms
        ):
            return self._fail(
                AdapterErrorCode.PERMISSION_MISMATCH,
                "Trading or withdrawal permissions are not allowed for verification.",
            )
        return uid, account_type, env_label

    def _fail(self, code: AdapterErrorCode, message: str) -> AdapterVerificationResult:
        _safe_log("bybit_testnet_verify_fail", reason=code.value)
        return AdapterVerificationResult(
            ok=False,
            reason=code.value,
            exchange_account_fingerprint=None,
            permission_class=None,
            environment=None,
            simulated=self._simulated,
            audited_at=_utc_now(),
            audit_event="bybit_testnet_verification_failed",
            safe_message=message,
        )


# Re-export deny reasons used by gates for convenience
__all__ = [
    "AdapterErrorCode",
    "AdapterVerificationResult",
    "BybitTestnetReadClient",
    "BybitTestnetVerificationAdapter",
    "FakeBybitScenario",
    "FakeBybitTestnetClient",
    "VerificationDenyReason",
]
