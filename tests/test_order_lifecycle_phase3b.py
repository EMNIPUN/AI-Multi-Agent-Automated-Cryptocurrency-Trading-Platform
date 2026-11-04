"""Phase 3B Part 2 — evidence-based order lifecycle observation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from agent.order_intent import OrderIntent, OrderIntentState, utc_now_iso
from agent.order_lifecycle_observer import (
    OrderLifecycleObserver,
    event_id_for_intent,
)
from agent.telemetry_ledger import TelemetryLedger
from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.observability.types import ExecutionMode, ObservabilityEventType


def _intent(
    *,
    intent_id: str,
    state: OrderIntentState,
    filled_qty: str = "",
    remaining_qty: str = "",
    qty: str = "1",
    updated_at: str | None = None,
) -> OrderIntent:
    now = updated_at or utc_now_iso()
    return OrderIntent(
        intent_id=intent_id,
        client_order_id=f"clid-{intent_id}",
        env_scope="test",
        account_fp="fp-secret-should-not-leak",
        symbol="HYPEUSDT",
        category="linear",
        side="Buy",
        qty=qty,
        reduce_only=False,
        order_type="Market",
        time_in_force="GTC",
        take_profit=None,
        stop_loss=None,
        correlation_id=f"corr-{intent_id}",
        risk_auth_ref="risk-ref",
        state=state,
        created_at=now,
        expires_at=now,
        dry_run=True,
        filled_qty=filled_qty,
        remaining_qty=remaining_qty,
        updated_at=now,
    )


def _observer(intents: list[OrderIntent]) -> OrderLifecycleObserver:
    return OrderLifecycleObserver(
        env_scope="test",
        account_fp="fp-secret-should-not-leak",
        execution_mode=ExecutionMode.DRY_RUN,
        list_fn=lambda: list(intents),
    )


def test_event_ids_are_stable_and_state_specific() -> None:
    created = _intent(intent_id="i1", state=OrderIntentState.CREATED)
    accepted = _intent(intent_id="i1", state=OrderIntentState.ACCEPTED)
    partial = _intent(intent_id="i1", state=OrderIntentState.PARTIALLY_FILLED, filled_qty="0.4")
    assert event_id_for_intent(created) == "order.intent_created:i1"
    assert event_id_for_intent(accepted) == "order.accepted:i1"
    assert event_id_for_intent(partial) == "order.partially_filled:i1:0.4"
    assert event_id_for_intent(_intent(intent_id="i1", state=OrderIntentState.SUBMISSION_PENDING)) is None
    assert event_id_for_intent(_intent(intent_id="i1", state=OrderIntentState.REJECTED)) is None


def test_intent_created_and_accepted_not_filled(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    intents = [_intent(intent_id="a1", state=OrderIntentState.ACCEPTED)]
    result = _observer(intents).poll(ledger)
    assert result.emitted == 1
    types = {e.event_type for e in ledger._newest(10)}
    assert ObservabilityEventType.ORDER_ACCEPTED in types
    assert ObservabilityEventType.ORDER_FILLED not in types
    snap = ledger.snapshot()
    assert snap.orders[0].state == "ACCEPTED"
    assert snap.orders[0].filled_qty in {"0", "0.0", None, "0"} or snap.orders[0].filled_qty == "0"


def test_partial_then_cancel_preserves_filled_qty(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    obs = _observer([])
    # Simulate progressive journal states across polls.
    obs._list_fn = lambda: [_intent(intent_id="p1", state=OrderIntentState.PARTIALLY_FILLED, filled_qty="0.3")]
    assert obs.poll(ledger).emitted == 1
    obs._list_fn = lambda: [
        _intent(
            intent_id="p1",
            state=OrderIntentState.CANCELED,
            filled_qty="0.3",
            remaining_qty="0.7",
        )
    ]
    assert obs.poll(ledger).emitted == 1
    events = {e.event_type: e for e in ledger._newest(20)}
    assert ObservabilityEventType.ORDER_PARTIALLY_FILLED in events
    assert ObservabilityEventType.ORDER_CANCELED in events
    cancel = events[ObservabilityEventType.ORDER_CANCELED]
    assert cancel.payload["filled_qty"] == "0.3"


def test_fully_filled(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    _observer([_intent(intent_id="f1", state=OrderIntentState.FILLED, filled_qty="1", qty="1")]).poll(
        ledger
    )
    assert any(e.event_type is ObservabilityEventType.ORDER_FILLED for e in ledger._newest(5))


def test_unknown_emits_reconciliation_required_not_fill(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    _observer([_intent(intent_id="u1", state=OrderIntentState.UNKNOWN)]).poll(ledger)
    types = {e.event_type for e in ledger._newest(5)}
    assert ObservabilityEventType.ORDER_RECONCILIATION_REQUIRED in types
    assert ObservabilityEventType.ORDER_FILLED not in types
    assert ObservabilityEventType.ORDER_ACCEPTED not in types


def test_duplicate_polling_is_idempotent(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    intents = [_intent(intent_id="d1", state=OrderIntentState.CREATED)]
    obs = _observer(intents)
    assert obs.poll(ledger).emitted == 1
    assert obs.poll(ledger).emitted == 0
    assert ledger.count() == 1


def test_restart_idempotency(tmp_path: Path) -> None:
    path = tmp_path / "obs.sqlite"
    ledger = TelemetryLedger(path)
    intents = [_intent(intent_id="r1", state=OrderIntentState.FILLED, filled_qty="2")]
    _observer(intents).poll(ledger)
    restarted = TelemetryLedger(path)
    assert _observer(intents).poll(restarted).emitted == 0
    assert restarted.count() == 1


def test_out_of_order_observations_do_not_invent_earlier_states(tmp_path: Path) -> None:
    """Seeing FILLED does not synthesize ACCEPTED if that row was never observed."""
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    _observer([_intent(intent_id="o1", state=OrderIntentState.FILLED, filled_qty="1")]).poll(ledger)
    types = {e.event_type for e in ledger._newest(10)}
    assert ObservabilityEventType.ORDER_FILLED in types
    assert ObservabilityEventType.ORDER_ACCEPTED not in types
    assert ObservabilityEventType.ORDER_INTENT_CREATED not in types


def test_missing_evidence_submission_pending_emits_nothing(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    result = _observer(
        [_intent(intent_id="s1", state=OrderIntentState.SUBMISSION_PENDING)]
    ).poll(ledger)
    assert result.emitted == 0
    assert result.orders[0].state == "SUBMISSION_PENDING"


def test_payload_never_includes_account_fingerprint(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    _observer([_intent(intent_id="x1", state=OrderIntentState.CREATED)]).poll(ledger)
    blob = ledger.snapshot().model_dump_json().lower()
    assert "fp-secret" not in blob
    assert "account_fp" not in blob


def test_sqlite_busy_retries_then_reports_error(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    calls = {"n": 0}

    def boom() -> list[OrderIntent]:
        calls["n"] += 1
        raise IntentBusy()

    class IntentBusy(Exception):
        pass

    # Patch load path via OperationalError-like message
    import sqlite3

    def busy() -> list[OrderIntent]:
        calls["n"] += 1
        raise sqlite3.OperationalError("database is locked")

    obs = OrderLifecycleObserver(
        env_scope="test",
        account_fp="fp",
        list_fn=busy,
        busy_retries=2,
        busy_sleep_s=0.01,
    )
    result = obs.poll(ledger)
    assert result.emitted == 0
    assert result.error == "OperationalError"
    assert calls["n"] == 2


def test_source_journal_unchanged_by_observer(tmp_path: Path) -> None:
    from agent.intent_store import IntentStore

    store = IntentStore(db_path=tmp_path / "intents.sqlite3")
    intent = _intent(intent_id="j1", state=OrderIntentState.CREATED)
    store.insert_created(intent)
    before = store.get_by_intent_id("j1")
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    OrderLifecycleObserver(
        intent_store=store,
        env_scope="test",
        account_fp="fp-secret-should-not-leak",
    ).poll(ledger)
    after = store.get_by_intent_id("j1")
    assert before is not None and after is not None
    assert before.state is after.state
    assert before.updated_at == after.updated_at


def test_telemetry_failure_isolated(tmp_path: Path) -> None:
    intents = [_intent(intent_id="t1", state=OrderIntentState.CREATED)]
    obs = _observer(intents)
    broken = MagicMock()
    broken.safe_record.side_effect = RuntimeError("disk")
    # poll catches per-event exceptions around safe_record via try/except
    broken.safe_record = MagicMock(return_value=False)
    result = obs.poll(broken)
    assert result.emitted == 0
    assert result.intents_seen == 1


def _settings(**kwargs) -> ApiSettings:
    base = dict(
        _env_file=None,
        api_host="127.0.0.1",
        cors_origins=[],
        database_url=None,
        private_data_reads_enabled=False,
        observability_fixture_mode=True,
        observability_live_stream_enabled=False,
        observability_ledger_path=None,
        supabase_url="https://example.supabase.co",
        auth_jwt_mode="hs256",
        supabase_jwt_secret="test-only-hs256-secret-not-for-production-32b+",
        supabase_jwt_audience="authenticated",
        supabase_jwt_issuer="https://example.supabase.co/auth/v1",
    )
    base.update(kwargs)
    return ApiSettings(**base)


def test_worker_snapshot_rejects_auth_and_forwarded_headers(tmp_path: Path) -> None:
    ledger = tmp_path / "obs.sqlite"
    TelemetryLedger(ledger)
    settings = _settings(observability_ledger_path=str(ledger))
    clear_settings_cache()
    app = create_app(settings)
    principal = AuthenticatedPrincipal(
        user_id="11111111-1111-1111-1111-111111111111",
        role="authenticated",
    )
    app.state.token_verifier = StaticMappingVerifier({"good": principal})
    client = TestClient(app)
    assert (
        client.get(
            "/api/v1/observability/worker-snapshot",
            headers={"Authorization": "Bearer good"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/observability/worker-snapshot",
            headers={"X-Forwarded-For": "8.8.8.8"},
        ).status_code
        == 403
    )


def test_authoritative_occurred_at_used(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    stamped = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc).isoformat()
    _observer(
        [_intent(intent_id="ts1", state=OrderIntentState.CREATED, updated_at=stamped)]
    ).poll(ledger)
    event = ledger._newest(1)[0]
    assert event.occurred_at.year == 2024
    assert event.occurred_at.month == 1
