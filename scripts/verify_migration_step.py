"""Post-step verification after Alembic upgrades (read-only assertions; no secrets)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import create_engine, text

from apps.api.app.database_url import inspect_database_url, normalize_database_url
from scripts.verify_dev_database_target import extract_project_ref


def _engine():
    raw = (os.environ.get("DATABASE_URL") or "").strip()
    if not raw:
        raise SystemExit("NO_DATABASE_URL")
    return create_engine(normalize_database_url(raw), pool_pre_ping=True)


def verify_after_0002() -> None:
    eng = _engine()
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        ver = c.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        assert ver == "20261104_0002", f"unexpected revision {ver}"
        for t in ("agent_decisions", "system_events", "strategy_configs"):
            has = c.execute(
                text(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='app' AND table_name=:t AND column_name='owner_user_id'
                    """
                ),
                {"t": t},
            ).scalar()
            assert has, f"missing owner_user_id on {t}"
            rls = c.execute(
                text(
                    """
                    SELECT c.relrowsecurity FROM pg_class c
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='app' AND c.relname=:t
                    """
                ),
                {"t": t},
            ).scalar()
            assert rls is True, f"RLS not enabled on {t}"
        pols = [
            r[0]
            for r in c.execute(
                text(
                    "SELECT policyname FROM pg_policies WHERE schemaname='app' ORDER BY 1"
                )
            )
        ]
        for need in (
            "agent_decisions_select_own",
            "system_events_select_own",
            "strategy_configs_select_own",
        ):
            assert need in pols, f"missing policy {need}"
        idx = [
            r[0]
            for r in c.execute(
                text(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE schemaname='app' AND tablename='strategy_configs'
                    """
                )
            )
        ]
        assert "ix_strategy_configs_owner_name" in idx
        assert "ix_strategy_configs_name" not in idx
        for t in ("agent_decisions", "system_events", "strategy_configs"):
            n = c.execute(text(f"SELECT COUNT(*) FROM app.{t}")).scalar()
            assert n == 0, f"unexpected rows in {t}: {n}"
    eng.dispose()
    print("VERIFY_0002_OK")


def verify_after_0003() -> None:
    eng = _engine()
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        ver = c.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        assert ver == "20261105_0003", f"unexpected revision {ver}"
        exists = c.execute(
            text(
                """
                SELECT 1 FROM pg_tables
                WHERE schemaname='app' AND tablename='exchange_account_bindings'
                """
            )
        ).scalar()
        assert exists, "exchange_account_bindings missing"
        rls = c.execute(
            text(
                """
                SELECT c.relrowsecurity FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='app' AND c.relname='exchange_account_bindings'
                """
            )
        ).scalar()
        assert rls is True
        pols = [
            r[0]
            for r in c.execute(
                text(
                    """
                    SELECT policyname FROM pg_policies
                    WHERE schemaname='app' AND tablename='exchange_account_bindings'
                    """
                )
            )
        ]
        assert "exchange_account_bindings_select_own" in pols
        idx = [
            r[0]
            for r in c.execute(
                text(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE schemaname='app' AND tablename='exchange_account_bindings'
                    ORDER BY 1
                    """
                )
            )
        ]
        for need in (
            "ix_exchange_bindings_telemetry_scope",
            "ix_exchange_bindings_active_cred",
            "ix_exchange_bindings_owner_active_env",
        ):
            assert need in idx, f"missing index {need}; have={idx}"
        n = c.execute(text("SELECT COUNT(*) FROM app.exchange_account_bindings")).scalar()
        assert n == 0
        # Still empty catalog
        for t in ("agent_decisions", "system_events", "strategy_configs"):
            assert c.execute(text(f"SELECT COUNT(*) FROM app.{t}")).scalar() == 0
    eng.dispose()
    print("VERIFY_0003_OK")


def confirm_identity() -> None:
    raw = os.environ["DATABASE_URL"]
    info = inspect_database_url(raw)
    ref = extract_project_ref(host=info.host, user=info.user)
    assert ref == "wmirifmgaftassgrfbyl", ref
    print("IDENTITY_OK", info.host, ref)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "identity":
        confirm_identity()
    elif cmd == "0002":
        verify_after_0002()
    elif cmd == "0003":
        verify_after_0003()
    else:
        raise SystemExit("usage: verify_migration_step.py identity|0002|0003")
