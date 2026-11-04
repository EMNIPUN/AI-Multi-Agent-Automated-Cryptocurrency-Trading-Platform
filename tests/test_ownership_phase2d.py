"""Phase 2D offline ownership / isolation tests — local SQLite + mock JWT only."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.catalog_service import (
    CatalogReadContext,
    list_agent_decisions,
    parse_owner_uuid,
)
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.deps import require_private_catalog_access
from apps.api.app.factory import create_app
from apps.api.app.migration_audit import audit_initial_migration, audit_ownership_migration
from apps.api.app.models import AgentDecision, Base, StrategyConfig, SystemEvent
from apps.api.app.ownership import assert_owner_matches
from apps.api.app.routers import catalog as catalog_router
from apps.api.app.sanitize import sanitize_public_json
from apps.api.app.schemas import PaginationQuery


USER_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _settings(**kwargs) -> ApiSettings:
    base = dict(
        _env_file=None,
        api_host="127.0.0.1",
        cors_origins=[],
        database_url=None,
        supabase_url="https://example.supabase.co",
        auth_jwt_mode="hs256",
        supabase_jwt_secret="test-only-hs256-secret-not-for-production-32b+",
        supabase_jwt_audience="authenticated",
        supabase_jwt_issuer="https://example.supabase.co/auth/v1",
        private_data_reads_enabled=False,
    )
    base.update(kwargs)
    return ApiSettings(**base)


def _principal(user_id: uuid.UUID | str = USER_A) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=str(user_id),
        role="authenticated",
        email="a@example.com",
        scopes=("read:self",),
    )


@pytest.fixture(autouse=True)
def _clear_settings() -> Generator[None, None, None]:
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def catalog_session(tmp_path: Path) -> Generator[Session, None, None]:
    """SQLite with attached `app` schema matching SQLAlchemy models."""
    main = tmp_path / "main.sqlite"
    app_db = tmp_path / "app.sqlite"
    engine = create_engine(f"sqlite:///{main.as_posix()}", future=True)
    with engine.begin() as conn:
        conn.execute(text(f"ATTACH DATABASE '{app_db.as_posix()}' AS app"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed(session: Session) -> None:
    now = datetime.now(timezone.utc)
    session.add_all(
        [
            AgentDecision(
                id=uuid.uuid4(),
                created_at=now,
                updated_at=now,
                owner_user_id=USER_A,
                env_scope="local",
                account_fp="fp-a-secret",
                symbol="BTCUSDT",
                category="linear",
                action="buy",
                strategy_id="s1",
                reason="owned-a",
                payload_json={"note": "ok", "api_key": "SHOULD_NOT_LEAK", "token": "x"},
            ),
            AgentDecision(
                id=uuid.uuid4(),
                created_at=now,
                updated_at=now,
                owner_user_id=USER_B,
                env_scope="local",
                account_fp="fp-b-secret",
                symbol="ETHUSDT",
                category="linear",
                action="sell",
                strategy_id="s2",
                reason="owned-b",
                payload_json={"note": "b"},
            ),
            AgentDecision(
                id=uuid.uuid4(),
                created_at=now,
                updated_at=now,
                owner_user_id=None,
                env_scope="local",
                account_fp="fp-unowned",
                symbol="SOLUSDT",
                category="linear",
                action="hold",
                strategy_id="s0",
                reason="unowned",
                payload_json={"note": "null-owner"},
            ),
            SystemEvent(
                id=uuid.uuid4(),
                created_at=now,
                owner_user_id=USER_A,
                env_scope="local",
                severity="info",
                event_type="worker_heartbeat",
                message="ok",
                details_json={"password": "nope", "count": 1},
            ),
            SystemEvent(
                id=uuid.uuid4(),
                created_at=now,
                owner_user_id=USER_A,
                env_scope="local",
                severity="error",
                event_type="api_key_event",
                message="blocked type",
                details_json={"secret": "x"},
            ),
            SystemEvent(
                id=uuid.uuid4(),
                created_at=now,
                owner_user_id=USER_B,
                env_scope="local",
                severity="info",
                event_type="worker_heartbeat",
                message="b-only",
                details_json={},
            ),
            StrategyConfig(
                id=uuid.uuid4(),
                created_at=now,
                updated_at=now,
                owner_user_id=USER_A,
                name="alpha",
                version="1",
                enabled=True,
                config_json={"lookback": 20, "api_secret": "hidden"},
            ),
            StrategyConfig(
                id=uuid.uuid4(),
                created_at=now,
                updated_at=now,
                owner_user_id=USER_B,
                name="alpha",
                version="1",
                enabled=False,
                config_json={"lookback": 5},
            ),
            StrategyConfig(
                id=uuid.uuid4(),
                created_at=now,
                updated_at=now,
                owner_user_id=None,
                name="legacy",
                version="1",
                enabled=False,
                config_json={},
            ),
        ]
    )
    session.commit()


def _client_with_session(
    session: Session,
    *,
    settings: ApiSettings | None = None,
    principals: dict[str, AuthenticatedPrincipal] | None = None,
) -> TestClient:
    clear_settings_cache()
    settings = settings or _settings(private_data_reads_enabled=True)
    app = create_app(settings)
    principals = principals or {"good": _principal(USER_A), "user-b": _principal(USER_B)}
    app.state.token_verifier = StaticMappingVerifier(principals)

    def _override(
        page: PaginationQuery = Depends(catalog_router._pagination),
        principal: AuthenticatedPrincipal = Depends(require_private_catalog_access),
    ) -> Generator[CatalogReadContext, None, None]:
        # Re-bind to the same session for deterministic offline tests (no remote DB).
        yield CatalogReadContext(page=page, principal=principal, session=session)

    app.dependency_overrides[catalog_router.get_catalog_read_context] = _override
    return TestClient(app)


def test_private_flag_default_still_blocks() -> None:
    app = create_app(_settings(private_data_reads_enabled=False))
    app.state.token_verifier = StaticMappingVerifier({"good": _principal()})
    resp = TestClient(app).get(
        "/api/v1/agents/decisions",
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "ownership_schema_required"


def test_unauthenticated_rejected(catalog_session: Session) -> None:
    _seed(catalog_session)
    client = _client_with_session(catalog_session)
    assert client.get("/api/v1/agents/decisions").status_code == 401


def test_user_reads_only_owned_rows(catalog_session: Session) -> None:
    _seed(catalog_session)
    client = _client_with_session(catalog_session)
    resp = client.get(
        "/api/v1/agents/decisions",
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["reason"] == "owned-a"
    assert body["items"][0]["symbol"] == "BTCUSDT"
    # Raw account fingerprint must not appear in public schema
    assert "account_fp" not in body["items"][0]
    assert "fp-a-secret" not in resp.text
    assert "SHOULD_NOT_LEAK" not in resp.text
    assert body["items"][0]["payload_json"]["api_key"] == "[redacted]"
    assert body["items"][0]["payload_json"]["note"] == "ok"


def test_user_a_cannot_read_user_b(catalog_session: Session) -> None:
    _seed(catalog_session)
    client = _client_with_session(catalog_session)
    for path in (
        "/api/v1/agents/decisions",
        "/api/v1/system/events",
        "/api/v1/strategies",
    ):
        body = client.get(path, headers={"Authorization": "Bearer good"}).json()
        blob = str(body)
        assert "owned-b" not in blob
        assert "b-only" not in blob
        assert "ETHUSDT" not in blob or path != "/api/v1/agents/decisions"


def test_unowned_rows_inaccessible(catalog_session: Session) -> None:
    _seed(catalog_session)
    client = _client_with_session(catalog_session)
    dec = client.get(
        "/api/v1/agents/decisions",
        headers={"Authorization": "Bearer good"},
    ).json()
    assert all(i["reason"] != "unowned" for i in dec["items"])
    strat = client.get(
        "/api/v1/strategies",
        headers={"Authorization": "Bearer good"},
    ).json()
    assert all(i["name"] != "legacy" for i in strat["items"])


def test_strategies_and_events_sanitized(catalog_session: Session) -> None:
    _seed(catalog_session)
    client = _client_with_session(catalog_session)
    events = client.get(
        "/api/v1/system/events",
        headers={"Authorization": "Bearer good"},
    ).json()
    assert len(events["items"]) == 1
    assert events["items"][0]["event_type"] == "worker_heartbeat"
    assert events["items"][0]["details_json"]["password"] == "[redacted]"
    assert events["items"][0]["details_json"]["count"] == 1

    strategies = client.get(
        "/api/v1/strategies",
        headers={"Authorization": "Bearer good"},
    ).json()
    assert len(strategies["items"]) == 1
    assert strategies["items"][0]["name"] == "alpha"
    assert strategies["items"][0]["config_json"]["api_secret"] == "[redacted]"
    assert strategies["items"][0]["config_json"]["lookback"] == 20


def test_pagination_ordering(catalog_session: Session) -> None:
    now = datetime.now(timezone.utc)
    for i in range(3):
        catalog_session.add(
            AgentDecision(
                id=uuid.uuid4(),
                created_at=now.replace(microsecond=i),
                updated_at=now,
                owner_user_id=USER_A,
                env_scope="local",
                account_fp="",
                symbol=f"S{i}",
                category="linear",
                action="buy",
                strategy_id="s",
                reason=f"r{i}",
            )
        )
    catalog_session.commit()
    client = _client_with_session(catalog_session)
    page = client.get(
        "/api/v1/agents/decisions?limit=2&offset=0",
        headers={"Authorization": "Bearer good"},
    ).json()
    assert len(page["items"]) == 2
    assert page["limit"] == 2
    assert page["offset"] == 0
    # Stable newest-first
    assert page["items"][0]["created_at"] >= page["items"][1]["created_at"]


def test_query_failure_fail_closed(catalog_session: Session) -> None:
    client = _client_with_session(catalog_session)

    class BoomSession:
        def scalars(self, *_a, **_k):
            raise RuntimeError("owner_user_id does not exist")

    def _boom(
        page: PaginationQuery = Depends(catalog_router._pagination),
        principal: AuthenticatedPrincipal = Depends(require_private_catalog_access),
    ) -> Generator[CatalogReadContext, None, None]:
        yield CatalogReadContext(page=page, principal=principal, session=BoomSession())  # type: ignore[arg-type]

    app = create_app(_settings(private_data_reads_enabled=True))
    app.state.token_verifier = StaticMappingVerifier({"good": _principal()})
    app.dependency_overrides[catalog_router.get_catalog_read_context] = _boom
    resp = TestClient(app).get(
        "/api/v1/agents/decisions",
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "ownership_schema_unavailable"


def test_missing_db_fail_closed_when_flag_enabled() -> None:
    app = create_app(_settings(private_data_reads_enabled=True, database_url=None))
    app.state.token_verifier = StaticMappingVerifier({"good": _principal()})
    resp = TestClient(app).get(
        "/api/v1/strategies",
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "database_not_configured"


def test_jwt_still_required_when_flag_enabled() -> None:
    app = create_app(_settings(private_data_reads_enabled=True))
    app.state.token_verifier = StaticMappingVerifier({})
    assert TestClient(app).get("/api/v1/strategies").status_code == 401


def test_sanitize_redacts_nested() -> None:
    cleaned = sanitize_public_json(
        {"ok": 1, "nested": {"refresh_token": "abc", "x": "y"}, "list": [{"password": "p"}]}
    )
    assert cleaned["ok"] == 1
    assert cleaned["nested"]["refresh_token"] == "[redacted]"
    assert cleaned["nested"]["x"] == "y"
    assert cleaned["list"][0]["password"] == "[redacted]"


def test_assert_owner_matches_null() -> None:
    with pytest.raises(Exception) as exc:
        assert_owner_matches(_principal(), None)
    assert getattr(exc.value, "status_code", None) == 403


def test_parse_owner_uuid() -> None:
    assert parse_owner_uuid(_principal(USER_A)) == USER_A
    with pytest.raises(Exception) as exc:
        parse_owner_uuid(_principal("not-a-uuid"))
    assert getattr(exc.value, "status_code", None) == 403


def test_service_layer_cross_user_empty(catalog_session: Session) -> None:
    _seed(catalog_session)
    ctx = CatalogReadContext(
        page=PaginationQuery(limit=20, offset=0),
        principal=_principal(USER_A),
        session=catalog_session,
    )
    result = list_agent_decisions(ctx)
    assert len(result.items) == 1
    assert result.items[0].reason == "owned-a"


def test_migration_audits_pass() -> None:
    initial = audit_initial_migration()
    assert initial.ok, initial.issues
    ownership = audit_ownership_migration()
    assert ownership.ok, ownership.issues
    assert any("0002" in f for f in ownership.revision_files)


def test_review_sql_artifact_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    sql = root / "apps" / "api" / "sql" / "review" / "20261104_0002_ownership_rls.sql"
    text_sql = sql.read_text(encoding="utf-8")
    assert "owner_user_id" in text_sql
    assert "ENABLE ROW LEVEL SECURITY" in text_sql
    assert "auto-apply" in text_sql.lower()
    # Executable GRANT must not appear (comments mentioning the phrase are OK).
    executable = "\n".join(
        line for line in text_sql.splitlines() if not line.lstrip().startswith("--")
    )
    assert "GRANT USAGE ON SCHEMA app TO anon" not in executable
    assert "GRANT " not in executable.upper()
    roles = (root / "apps" / "api" / "sql" / "runtime_role_recommendations.sql").read_text(
        encoding="utf-8"
    )
    assert "BYPASSRLS" in roles
    assert "auto-applied" in roles.lower()


def test_pool_isolation_no_set_role_in_catalog() -> None:
    src = Path(catalog_router.__file__).read_text(encoding="utf-8")
    # Strip docstrings/comments — ensure no executable SET ROLE / GUC usage.
    assert "session.execute" not in src or "SET ROLE" not in src
    assert "set_config(" not in src
    assert "text(\"SET" not in src and "text('SET" not in src
    assert "request.jwt.claim" not in src


def test_no_mutation_routes_in_catalog() -> None:
    src = Path(catalog_router.__file__).read_text(encoding="utf-8")
    assert "@router.post" not in src
    assert "@router.put" not in src
    assert "@router.patch" not in src
    assert "@router.delete" not in src


def test_user_b_sees_own_strategy(catalog_session: Session) -> None:
    _seed(catalog_session)
    client = _client_with_session(catalog_session)
    body = client.get(
        "/api/v1/strategies",
        headers={"Authorization": "Bearer user-b"},
    ).json()
    assert len(body["items"]) == 1
    assert body["items"][0]["enabled"] is False
    assert body["items"][0]["config_json"]["lookback"] == 5
