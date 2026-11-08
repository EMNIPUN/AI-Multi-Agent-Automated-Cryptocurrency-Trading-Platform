"""Option A — least-privilege local security tests (no remote DDL/DML)."""

from __future__ import annotations

import threading
import uuid
from unittest.mock import MagicMock

import pytest

from apps.api.app.security.db_identity import (
    IdentityLeakTracker,
    assert_write_owner_matches,
    attach_owner_identity,
    clear_owner_identity,
    parse_owner_uuid,
    require_attached_owner,
    runtime_db_identity_enabled,
)
from apps.api.app.security.session_identity import ConnectionIdentityGuard
from apps.api.app.signals.cloud_gates import get_signal_cloud_gates


def test_runtime_identity_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_DB_IDENTITY_ENABLED", raising=False)
    assert runtime_db_identity_enabled() is False


def test_parse_owner_uuid_fail_closed() -> None:
    with pytest.raises(ValueError, match="owner_identity_invalid_uuid"):
        parse_owner_uuid("not-a-uuid")
    with pytest.raises(ValueError, match="owner_identity_invalid_uuid"):
        parse_owner_uuid("")
    with pytest.raises(ValueError, match="owner_identity_invalid_uuid"):
        parse_owner_uuid("user@example.com")


def test_attach_without_guc_does_not_touch_session() -> None:
    session = MagicMock()
    owner = uuid.uuid4()
    attached = attach_owner_identity(session, owner_user_id=owner, apply_guc=False)
    assert attached.owner_user_id == owner
    session.execute.assert_not_called()
    clear_owner_identity(session, apply_guc=False)
    session.execute.assert_not_called()


def test_attach_with_guc_uses_bound_params() -> None:
    session = MagicMock()
    owner = uuid.uuid4()
    attach_owner_identity(session, owner_user_id=owner, apply_guc=True)
    assert session.execute.called
    _stmt, params = session.execute.call_args.args
    assert params["sub"] == str(owner)
    assert params["guc"] == "request.jwt.claim.sub"


def test_require_attached_owner_fail_closed() -> None:
    with pytest.raises(ValueError, match="owner_identity_missing"):
        require_attached_owner(None)


def test_assert_write_owner_matches() -> None:
    a = uuid.uuid4()
    b = uuid.uuid4()
    assert_write_owner_matches(principal_owner=a, row_owner=a)
    with pytest.raises(PermissionError, match="owner_mismatch"):
        assert_write_owner_matches(principal_owner=a, row_owner=b)


def test_pool_guard_resets_on_checkout_and_release() -> None:
    guard = ConnectionIdentityGuard()
    owner_a = uuid.uuid4()
    owner_b = uuid.uuid4()
    guard.checkout("c1")
    guard.attach_verified_user(connection_id="c1", user_id=owner_a)
    guard.assert_no_cross_tenant_leak("c1", expected_user_id=owner_a)
    guard.release("c1")
    guard.assert_no_cross_tenant_leak("c1", expected_user_id=None)
    # Reuse connection id — must not inherit prior tenant
    guard.checkout("c1")
    guard.assert_no_cross_tenant_leak("c1", expected_user_id=None)
    guard.attach_verified_user(connection_id="c1", user_id=owner_b)
    guard.assert_no_cross_tenant_leak("c1", expected_user_id=owner_b)


def test_pool_guard_rejects_attach_before_checkout() -> None:
    guard = ConnectionIdentityGuard()
    with pytest.raises(ValueError, match="connection_not_checked_out"):
        guard.attach_verified_user(connection_id="missing", user_id=uuid.uuid4())


def test_concurrent_request_identity_isolation() -> None:
    tracker = IdentityLeakTracker()
    owners = [uuid.uuid4() for _ in range(8)]
    errors: list[str] = []

    def worker(i: int) -> None:
        rid = f"r{i}"
        try:
            tracker.begin(rid, owners[i])
            tracker.assert_isolated(rid, owners[i])
            # Other owners must still be present without colliding on this key
            assert str(owners[i]) in tracker.active_owners()
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
        finally:
            tracker.end(rid)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert tracker.active_owners() == []


def test_cloud_write_gates_still_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED", "false")
    monkeypatch.setenv("SIGNAL_CLOUD_SYNC_ENABLED", "true")
    g = get_signal_cloud_gates()
    assert g.cloud_writes_allowed is False
    assert g.sync_allowed is False


def test_postgres_rls_harness_when_local_cluster_up() -> None:
    """Real PostgreSQL RLS via disposable local cluster (never Supabase)."""
    import socket
    from pathlib import Path
    import subprocess
    import sys

    sock = socket.socket()
    try:
        sock.settimeout(0.5)
        sock.connect(("127.0.0.1", 55432))
    except OSError:
        pytest.skip("Disposable local PG on 127.0.0.1:55432 not running")
    finally:
        sock.close()

    script = Path(__file__).resolve().parents[1] / "scripts" / "_option_a_local_pg_rls_harness.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
