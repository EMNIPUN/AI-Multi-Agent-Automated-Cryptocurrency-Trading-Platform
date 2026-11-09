"""
Phase 4D local→Supabase outbox sync worker (disabled until dual gates + owner binding).

Local SQLite remains authoritative for paper risk + scheduler lock.
Cloud rows are mirrors; unsynced outbox entries are never reported as cloud-confirmed.
"""

from __future__ import annotations

import logging
import random
import threading
import time
import uuid
from typing import Any, Protocol

from agent.multi_agent.decision_payload import (
    is_legacy_summary_payload,
    validate_decision_sync_payload,
)
from agent.multi_agent.signal_history_store import SignalHistoryStore
from apps.api.app.signals.cloud_gates import get_signal_cloud_gates
from apps.api.app.signals.cloud_repository import (
    SignalCloudWriteDenied,
    SqlAlchemySignalCloudRepository,
)
from apps.api.app.signals.owner_binding import resolve_sync_owner_binding

logger = logging.getLogger(__name__)

_BACKOFF_MS = (5_000, 15_000, 60_000, 300_000, 900_000, 1_800_000)
_MAX_ATTEMPTS_BEFORE_PERMANENT = 12
_DEFAULT_BATCH = 25
_LEASE_MS = 60_000


class _CommitSession(Protocol):
    def commit(self) -> None: ...

    def rollback(self) -> None: ...


def sync_health(store: SignalHistoryStore) -> dict[str, Any]:
    gates = get_signal_cloud_gates()
    stats = store.outbox_stats()
    binding = resolve_sync_owner_binding()
    return {
        **gates_public_safe(gates),
        "outbox": stats,
        "owner_binding": binding.public_dict(),
        "risk_authority": "local_sqlite_paper_risk_state",
        "scheduler_lock_authority": "local_sqlite_scheduler_lock",
        "cloud_authority": "mirror_after_sync_only",
        "conflict_policy": (
            "Local paper risk and scheduler lock win for process safety. "
            "Supabase mirrors are idempotent by decision_id/eval_key; "
            "never double-count risk from cloud retries."
        ),
        "execution_allowed": False,
        "trading_enabled": False,
        "private_api_used": False,
        "worker_default": "disabled",
    }


def gates_public_safe(gates: Any | None = None) -> dict[str, Any]:
    from apps.api.app.signals.cloud_gates import gates_public_dict

    if gates is None:
        return gates_public_dict()
    return {
        "signal_supabase_writes_enabled": gates.writes_enabled,
        "signal_supabase_writes_operator_approved": gates.operator_approved,
        "signal_cloud_sync_enabled": gates.sync_enabled,
        "cloud_writes_allowed": gates.cloud_writes_allowed,
        "sync_allowed": gates.sync_allowed,
    }


def _backoff_with_jitter(attempts: int) -> int:
    idx = min(max(0, int(attempts)), len(_BACKOFF_MS) - 1)
    base = _BACKOFF_MS[idx]
    return int(base * (0.75 + 0.5 * random.random()))


def _classify_error(exc: BaseException) -> tuple[bool, str]:
    """Return (permanent, code). Permanent errors must not retry forever."""
    text = str(exc)[:200]
    permanent_markers = (
        "payload_invalid",
        "legacy_summary_incomplete",
        "unsupported_event_type",
        "owner_user_id_invalid",
        "execution_allowed_must_be_false",
        "missing_decision",
    )
    lowered = text.lower()
    for m in permanent_markers:
        if m in lowered:
            return True, text
    if isinstance(exc, SignalCloudWriteDenied):
        # Gate denial while worker somehow running — retryable once gates open.
        return False, text
    return False, text


def drain_outbox_once(
    *,
    store: SignalHistoryStore,
    repo: SqlAlchemySignalCloudRepository,
    owner_user_id: uuid.UUID | None = None,
    now_ms: int,
    limit: int = _DEFAULT_BATCH,
    session: _CommitSession | None = None,
) -> dict[str, Any]:
    """
    Attempt a bounded sync drain.

    No-ops with reason when gates are closed or owner binding missing.
    Marks SYNCED only after successful cloud commit confirmation.
    """
    gates = get_signal_cloud_gates()
    if not gates.sync_allowed:
        return {
            "drained": 0,
            "synced": 0,
            "failed": 0,
            "permanent_failure": 0,
            "skipped_reason": "signal_cloud_sync_gated_off",
            **sync_health(store),
        }

    binding = resolve_sync_owner_binding()
    owner = owner_user_id or binding.owner_user_id
    if owner is None:
        return {
            "drained": 0,
            "synced": 0,
            "failed": 0,
            "permanent_failure": 0,
            "skipped_reason": binding.block_reason or "sync_owner_not_bound",
            **sync_health(store),
        }

    if store.outbox_backend() != "sqlite":
        return {
            "drained": 0,
            "synced": 0,
            "failed": 0,
            "permanent_failure": 0,
            "skipped_reason": "outbox_not_applicable_signal_history_is_authoritative",
            **sync_health(store),
        }

    recovered = store.recover_stale_in_progress(now_ms=now_ms)
    pending = store.claim_outbox_batch(
        now_ms=now_ms, limit=limit, lease_ms=_LEASE_MS
    )
    synced = 0
    failed = 0
    permanent = 0

    for item in pending:
        event_id = item["event_id"]
        attempts = int(item.get("attempts") or 0)
        if item["event_type"] != "signal_decision":
            store.mark_outbox_failed(
                event_id=event_id,
                error="unsupported_event_type",
                now_ms=now_ms,
                backoff_ms=_backoff_with_jitter(attempts),
                permanent=True,
            )
            permanent += 1
            continue

        payload = item.get("payload") or {}
        if is_legacy_summary_payload(payload):
            store.mark_outbox_failed(
                event_id=event_id,
                error="legacy_summary_incomplete",
                now_ms=now_ms,
                backoff_ms=_backoff_with_jitter(attempts),
                permanent=True,
            )
            permanent += 1
            continue

        ok, reason = validate_decision_sync_payload(payload)
        if not ok:
            store.mark_outbox_failed(
                event_id=event_id,
                error=f"payload_invalid:{reason}",
                now_ms=now_ms,
                backoff_ms=_backoff_with_jitter(attempts),
                permanent=True,
            )
            permanent += 1
            continue

        try:
            cloud_id = repo.upsert_decision_payload(
                owner_user_id=owner, payload=payload
            )
            if session is not None:
                try:
                    session.commit()
                except Exception as commit_exc:  # noqa: BLE001
                    # Ambiguous commit: do NOT mark SYNCED; leave for idempotent retry.
                    try:
                        session.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                    raise RuntimeError(
                        f"ambiguous_cloud_commit:{type(commit_exc).__name__}"
                    ) from commit_exc
            if cloud_id is None:
                raise RuntimeError("cloud_upsert_returned_none")
            store.mark_outbox_synced(event_id=event_id, now_ms=now_ms)
            synced += 1
        except Exception as exc:  # noqa: BLE001
            is_permanent, code = _classify_error(exc)
            if attempts + 1 >= _MAX_ATTEMPTS_BEFORE_PERMANENT:
                is_permanent = True
            store.mark_outbox_failed(
                event_id=event_id,
                error=code,
                now_ms=now_ms,
                backoff_ms=_backoff_with_jitter(attempts),
                permanent=is_permanent,
            )
            if is_permanent:
                permanent += 1
            else:
                failed += 1
            logger.info(
                "cloud_sync_item_failed event_id=%s permanent=%s err=%s",
                event_id,
                is_permanent,
                code,
            )

    return {
        "drained": len(pending),
        "synced": synced,
        "failed": failed,
        "permanent_failure": permanent,
        "stale_recovered": recovered,
        "owner_bound": True,
        **sync_health(store),
    }


class CloudSyncWorker:
    """
    Background drain loop — constructed only when explicitly started.
    Default application lifespan does NOT start this worker.
    """

    def __init__(
        self,
        *,
        store: SignalHistoryStore,
        repo_factory: Any,
        interval_s: float = 15.0,
        batch_limit: int = _DEFAULT_BATCH,
    ) -> None:
        self._store = store
        self._repo_factory = repo_factory
        self._interval_s = max(1.0, float(interval_s))
        self._batch_limit = batch_limit
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._metrics: dict[str, Any] = {
            "cycles": 0,
            "synced_total": 0,
            "failed_total": 0,
            "last_result": None,
        }

    @property
    def metrics(self) -> dict[str, Any]:
        return dict(self._metrics)

    def start(self) -> None:
        gates = get_signal_cloud_gates()
        if not gates.sync_allowed:
            raise RuntimeError("signal_cloud_sync_gated_off")
        if not resolve_sync_owner_binding().sync_owner_ready:
            raise RuntimeError("sync_owner_not_bound")
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="cryptonova-cloud-sync", daemon=True
        )
        self._thread.start()

    def stop(self, *, timeout_s: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout_s)

    def _run(self) -> None:
        while not self._stop.is_set():
            now_ms = int(time.time() * 1000)
            try:
                session, repo = self._repo_factory()
                result = drain_outbox_once(
                    store=self._store,
                    repo=repo,
                    now_ms=now_ms,
                    limit=self._batch_limit,
                    session=session,
                )
                self._metrics["cycles"] = int(self._metrics["cycles"]) + 1
                self._metrics["synced_total"] = int(self._metrics["synced_total"]) + int(
                    result.get("synced") or 0
                )
                self._metrics["failed_total"] = int(self._metrics["failed_total"]) + int(
                    result.get("failed") or 0
                )
                self._metrics["last_result"] = {
                    k: result.get(k)
                    for k in (
                        "drained",
                        "synced",
                        "failed",
                        "permanent_failure",
                        "skipped_reason",
                    )
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("cloud_sync_cycle_error err=%s", type(exc).__name__)
                self._metrics["last_result"] = {"error": type(exc).__name__}
            self._stop.wait(self._interval_s)
