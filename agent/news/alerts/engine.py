"""Critical news alert decisions (Prompt 69B). Advisory only — never trading instructions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from agent.news.schemas import ClassifiedEvent, Severity, VerificationStatus

_RANK = {
    Severity.UNKNOWN: 0,
    Severity.INFORMATIONAL: 1,
    Severity.LOW: 2,
    Severity.MEDIUM: 3,
    Severity.HIGH: 4,
    Severity.CRITICAL: 5,
}
_DOWN = (
    Severity.UNKNOWN,
    Severity.INFORMATIONAL,
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
    Severity.CRITICAL,
)
_FRESH_MS = 6 * 60 * 60 * 1000


def severity_rank(value: Severity | str) -> int:
    if isinstance(value, Severity):
        return _RANK[value]
    try:
        return _RANK[Severity(str(value))]
    except ValueError:
        return 0


def _downgrade(severity: Severity) -> Severity:
    idx = _DOWN.index(severity)
    return _DOWN[max(0, idx - 1)]


@dataclass(frozen=True)
class AlertPreference:
    alerts_enabled: bool = False
    min_severity: Severity = Severity.HIGH
    symbols: tuple[str, ...] = ()
    cooldown_ms: int = 1_800_000
    ttl_ms: int = 21_600_000
    in_app_enabled: bool = True
    telegram_enabled: bool = False


@dataclass(frozen=True)
class AlertDecision:
    create: bool
    reason: str
    severity: Severity
    warnings: tuple[str, ...]
    material_fingerprint: str
    idempotency_key: str
    explanation: str
    freshness: str
    agent_context: dict[str, Any] = field(default_factory=dict)


def material_fingerprint(event: ClassifiedEvent, severity: Severity) -> str:
    headline = " ".join((event.headline or "").lower().split())
    assets = ",".join(sorted(a.upper() for a in event.assets))
    raw = (
        f"{event.category.value}|{severity.value}|{event.verification.value}|"
        f"{headline}|{assets}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _freshness(event: ClassifiedEvent, now_ms: int) -> str:
    if event.published_at_ms is None and event.available_at_ms <= 0:
        return "unknown"
    anchor = event.available_at_ms or event.first_observed_at_ms
    if now_ms - anchor > _FRESH_MS:
        return "stale"
    return "fresh"


def _adjust(event: ClassifiedEvent, now_ms: int) -> tuple[Severity, tuple[str, ...], str]:
    """Reliability adjustments. Sentiment never sets severity."""
    warnings = list(event.warnings)
    severity = event.severity
    freshness = _freshness(event, now_ms)
    hard: set[str] = set()
    if "delayed_provider_feed" in warnings or any("delayed" in w for w in warnings):
        warnings.append("not_realtime_monitoring")
        hard.add("delayed_provider_feed")
    if event.published_at_ms is None:
        warnings.append("missing_publication_timestamp")
        hard.add("missing_publication_timestamp")
    if freshness == "stale":
        warnings.append("stale_event")
        hard.add("stale_event")
    if event.verification in {VerificationStatus.UNVERIFIED, VerificationStatus.UNKNOWN}:
        warnings.append("classification_uncertainty")
        hard.add("classification_uncertainty")
    if event.verification is VerificationStatus.SINGLE_SOURCE:
        warnings.append("single_source")
    official = event.verification is VerificationStatus.OFFICIAL_SOURCE
    if hard and not official and severity in {Severity.CRITICAL, Severity.HIGH}:
        severity = _downgrade(severity)
        warnings.append("severity_downgraded_for_uncertainty")
    # Dedup warnings while keeping order.
    seen: set[str] = set()
    ordered: list[str] = []
    for item in warnings:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return severity, tuple(ordered), freshness


def _agent_context(
    event: ClassifiedEvent,
    *,
    severity: Severity,
    freshness: str,
    warnings: tuple[str, ...],
    source_url: str | None,
) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "symbol": event.assets[0] if event.assets else None,
        "symbols": list(event.assets),
        "severity": severity.value,
        "verification": event.verification.value,
        "first_available_at_ms": event.available_at_ms,
        "freshness": freshness,
        "source_evidence": {
            "article_hashes": list(event.article_content_hashes),
            "source_url": source_url,
            "reason_codes": list(event.reason_codes),
        },
        "warnings": list(warnings),
        "advisory_only": True,
        "places_orders": False,
    }


def evaluate_alert(
    event: ClassifiedEvent,
    *,
    now_ms: int,
    preference: AlertPreference,
    prior: list[dict[str, Any]],
    source_url: str | None = None,
) -> AlertDecision:
    severity, warnings, freshness = _adjust(event, now_ms)
    fingerprint = material_fingerprint(event, severity)
    idem = f"{event.event_id}:{fingerprint}"
    context = _agent_context(
        event, severity=severity, freshness=freshness, warnings=warnings, source_url=source_url
    )
    explanation = (
        f"{severity.value} {event.category.value} for {', '.join(event.assets) or 'unspecified assets'}. "
        f"Verification {event.verification.value}. Freshness {freshness}. "
        "Sentiment is descriptive only and is not a market-direction signal. "
        + ("; ".join(warnings) if warnings else "No extra reliability warnings.")
    )

    def decision(create: bool, reason: str) -> AlertDecision:
        return AlertDecision(
            create=create,
            reason=reason,
            severity=severity,
            warnings=warnings,
            material_fingerprint=fingerprint,
            idempotency_key=idem,
            explanation=explanation,
            freshness=freshness,
            agent_context=context,
        )

    if not preference.alerts_enabled:
        return decision(False, "alerts_disabled")
    if preference.symbols:
        wanted = {s.upper() for s in preference.symbols}
        if not wanted.intersection(a.upper() for a in event.assets):
            return decision(False, "symbol_not_monitored")
    if severity_rank(severity) < severity_rank(preference.min_severity):
        return decision(False, "below_severity_threshold")

    same_event = [row for row in prior if row.get("event_id") == event.event_id]
    if any(row.get("idempotency_key") == idem for row in same_event):
        return decision(False, "duplicate_suppressed")
    if same_event and any(row.get("material_fingerprint") != fingerprint for row in same_event):
        return decision(True, "material_update")

    symbols = {a.upper() for a in event.assets}
    for row in prior:
        if row.get("event_id") == event.event_id:
            continue
        if str(row.get("status") or "") in {"EXPIRED", "SUPERSEDED"}:
            continue
        if int(row.get("expires_at_ms") or 0) < now_ms:
            continue
        if row.get("category") != event.category.value:
            continue
        row_symbols = {str(s).upper() for s in (row.get("symbols") or [])}
        if symbols and row_symbols and not symbols.intersection(row_symbols):
            continue
        age = now_ms - int(row.get("created_at_ms") or 0)
        if age > preference.cooldown_ms:
            continue
        if severity_rank(severity) > severity_rank(str(row.get("severity") or "UNKNOWN")):
            continue
        return decision(False, "cooldown_suppressed")
    return decision(True, "threshold_met")


def alert_row_from_decision(
    event: ClassifiedEvent,
    decision: AlertDecision,
    *,
    now_ms: int,
    owner_user_id: str | None,
    source_url: str | None,
    ttl_ms: int,
) -> dict[str, Any]:
    digest = hashlib.sha256(decision.idempotency_key.encode("utf-8")).hexdigest()[:20]
    return {
        "alert_id": f"nal_{digest}",
        "event_id": event.event_id,
        "owner_user_id": owner_user_id,
        "severity": decision.severity.value,
        "category": event.category.value,
        "status": "OPEN",
        "headline": event.headline,
        "summary": event.summary,
        "explanation": decision.explanation,
        "symbols": list(event.assets),
        "verification": event.verification.value,
        "source_url": source_url,
        "article_hashes": list(event.article_content_hashes),
        "published_at_ms": event.published_at_ms,
        "first_observed_at_ms": event.first_observed_at_ms,
        "detected_at_ms": now_ms,
        "available_at_ms": event.available_at_ms,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
        "acknowledged_at_ms": None,
        "expires_at_ms": now_ms + ttl_ms,
        "material_fingerprint": decision.material_fingerprint,
        "idempotency_key": decision.idempotency_key,
        "warnings": list(decision.warnings),
        "evidence": decision.agent_context.get("source_evidence") or {},
        "freshness": decision.freshness,
        "agent_context": decision.agent_context,
        "reason": decision.reason,
    }
