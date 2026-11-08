"""
Transactional PostgreSQL RLS isolation probe (Class C).

Defaults to DRY-RUN (read-only preflight). Write/SET ROLE execution requires:
  CRYPTONOVA_APPROVE_TRANSACTIONAL_RLS=yes
  CRYPTONOVA_DATA_API_APP_NOT_EXPOSED=yes
  --execute

Never commits. Always attempts ROLLBACK on the probe transaction.
Never prints DATABASE_URL, passwords, or JWT material.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from apps.api.app.database_url import normalize_database_url
from scripts.verify_dev_database_target import (
    DevTargetError,
    resolve_dev_database_url,
    summarize_identity,
    verify_dev_database_target,
)

# Load root .env for DATABASE_URL / identity vars. Do not override explicit shell flags.
load_dotenv(_ROOT / ".env", override=False)

EXPECTED_REVISION = "20261105_0003"
MARKER = "phase3c_part5b_rls_synth"
USER_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
USER_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2")
USER_INVALID = uuid.UUID("cccccccc-cccc-4ccc-8ccc-ccccccccccc3")

TABLES = (
    "agent_decisions",
    "system_events",
    "strategy_configs",
    "exchange_account_bindings",
)


class RlsProbeError(RuntimeError):
    """Fail-closed probe error (safe message only)."""


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _assert_eq(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise RlsProbeError(f"assertion_failed:{label}:expected={expected}:actual={actual}")


def _require_identity() -> dict[str, object]:
    try:
        identity = verify_dev_database_target(
            require_migration_approval=False, connect=False
        )
    except DevTargetError as exc:
        raise RlsProbeError(f"identity_rejected:{exc}") from exc
    if identity.project_ref != "wmirifmgaftassgrfbyl":
        raise RlsProbeError("unexpected_project_ref")
    if "supabase" not in (identity.host or "").lower() and identity.host not in {
        "localhost",
        "127.0.0.1",
    }:
        # approved remote must be supabase-like (already enforced by guard)
        pass
    return summarize_identity(identity)


def _connect() -> Engine:
    raw = resolve_dev_database_url(os.environ)
    url = normalize_database_url(raw, require_ssl_for_remote=True)
    return create_engine(url, pool_pre_ping=True)


def dry_run_preflight(conn: Connection) -> dict[str, object]:
    """Read-only checks — no GRANTs, inserts, or SET ROLE."""
    conn.execute(text("SET TRANSACTION READ ONLY"))
    rev = conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
    _assert_eq("alembic_revision", rev, EXPECTED_REVISION)

    can_set = bool(
        conn.execute(
            text("SELECT pg_has_role(current_user, 'authenticated', 'member')")
        ).scalar()
    )
    if not can_set:
        raise RlsProbeError("cannot_set_role_authenticated:current_user_not_member")

    # Required NOT NULL columns for planned inserts
    strategy_id_null = conn.execute(
        text(
            """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_schema='app' AND table_name='agent_decisions'
              AND column_name='strategy_id'
            """
        )
    ).scalar()
    _assert_eq("agent_decisions.strategy_id_nullable", strategy_id_null, "NO")

    # Confirm planned UUIDs parse
    for u in (USER_A, USER_B, USER_INVALID):
        uuid.UUID(str(u))

    # Residual synth rows must be zero before a real run
    residual = {
        "agent_decisions": int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM app.agent_decisions "
                    f"WHERE reason LIKE :m"
                ),
                {"m": f"{MARKER}%"},
            ).scalar()
            or 0
        ),
        "system_events": int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM app.system_events "
                    f"WHERE message LIKE :m"
                ),
                {"m": f"{MARKER}%"},
            ).scalar()
            or 0
        ),
        "strategy_configs": int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM app.strategy_configs "
                    f"WHERE name LIKE :m"
                ),
                {"m": f"{MARKER}%"},
            ).scalar()
            or 0
        ),
        "bindings": int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM app.exchange_account_bindings "
                    f"WHERE enrollment_attestation LIKE :m"
                ),
                {"m": f"{MARKER}%"},
            ).scalar()
            or 0
        ),
    }
    if any(residual.values()):
        raise RlsProbeError(f"residual_synth_rows_present:{residual}")

    grants = {
        "schema_usage": bool(
            conn.execute(
                text("SELECT has_schema_privilege('authenticated', 'app', 'USAGE')")
            ).scalar()
        ),
        "table_select": {
            t: bool(
                conn.execute(
                    text("SELECT has_table_privilege('authenticated', 'app.' || :t, 'SELECT')"),
                    {"t": t},
                ).scalar()
            )
            for t in TABLES
        },
    }
    if grants["schema_usage"] or any(grants["table_select"].values()):
        raise RlsProbeError(f"unexpected_persistent_grants:{grants}")

    bypass = bool(
        conn.execute(
            text(
                "SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname = current_user"
            )
        ).scalar()
    )
    return {
        "alembic": rev,
        "can_set_role_authenticated": can_set,
        "current_role_bypassrls": bypass,
        "residual_synth_rows": residual,
        "persistent_grants": grants,
        "insert_fix": "agent_decisions.strategy_id_required",
    }


def _set_jwt_sub(conn: Connection, sub: str) -> None:
    conn.execute(text("SELECT set_config('request.jwt.claim.sub', :s, true)"), {"s": sub})
    conn.execute(
        text("SELECT set_config('request.jwt.claim.role', 'authenticated', true)")
    )


def _count(conn: Connection, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar() or 0)


def execute_probe(conn: Connection) -> dict[str, object]:
    """
    Single-connection transactional probe. Never commits.
    Caller must only invoke after approval + Data API gate.
    """
    results: dict[str, object] = {}
    trans = conn.begin()
    try:
        rev = conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        _assert_eq("alembic_revision", rev, EXPECTED_REVISION)

        # Inserts as privileged role (BYPASSRLS). Include NOT NULL columns without DB defaults.
        conn.execute(
            text(
                """
                INSERT INTO app.agent_decisions (
                  id, owner_user_id, env_scope, account_fp, symbol, category,
                  action, strategy_id, reason
                ) VALUES
                  ('a1111111-1111-4111-8111-111111111111', :a, 'dev', '', 'BTCUSDT',
                   'linear', 'hold', '', :ma),
                  ('b1111111-1111-4111-8111-111111111111', :b, 'dev', '', 'ETHUSDT',
                   'linear', 'hold', '', :mb)
                """
            ),
            {"a": str(USER_A), "b": str(USER_B), "ma": f"{MARKER}_a", "mb": f"{MARKER}_b"},
        )
        conn.execute(
            text(
                """
                INSERT INTO app.system_events (
                  id, owner_user_id, env_scope, severity, event_type, message
                ) VALUES
                  ('a2222222-2222-4222-8222-222222222222', :a, 'dev', 'info', 'rls_probe', :ma),
                  ('b2222222-2222-4222-8222-222222222222', :b, 'dev', 'info', 'rls_probe', :mb)
                """
            ),
            {"a": str(USER_A), "b": str(USER_B), "ma": f"{MARKER}_a", "mb": f"{MARKER}_b"},
        )
        conn.execute(
            text(
                """
                INSERT INTO app.strategy_configs (
                  id, owner_user_id, name, version, enabled, config_json
                ) VALUES
                  ('a3333333-3333-4333-8333-333333333333', :a, :na, '1', false, '{}'::jsonb),
                  ('b3333333-3333-4333-8333-333333333333', :b, :nb, '1', false, '{}'::jsonb)
                """
            ),
            {
                "a": str(USER_A),
                "b": str(USER_B),
                "na": f"{MARKER}_a",
                "nb": f"{MARKER}_b",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO app.exchange_account_bindings (
                  id, owner_user_id, provider, environment, status, display_label,
                  credential_ref, telemetry_scope_id, enrollment_attestation,
                  enrolled_by_operator
                ) VALUES
                  ('a4444444-4444-4444-8444-444444444441', :a, 'bybit', 'testnet', 'active',
                   'synth-a-active', 'env:BYBIT_TESTNET_OPERATOR',
                   'a4444444-4444-4444-8444-444444444441', :aa, true),
                  ('b4444444-4444-4444-8444-444444444442', :b, 'bybit', 'testnet', 'active',
                   'synth-b-active', 'env:BYBIT_OPERATOR',
                   'b4444444-4444-4444-8444-444444444442', :ba, true),
                  ('a4444444-4444-4444-8444-444444444443', :a, 'bybit', 'demo', 'pending',
                   'synth-a-pending', 'env:BYBIT_DEMO_OPERATOR',
                   'a4444444-4444-4444-8444-444444444443', :ap, true),
                  ('a4444444-4444-4444-8444-444444444444', :a, 'bybit', 'mainnet', 'revoked',
                   'synth-a-revoked', 'env:BYBIT_MAINNET_OPERATOR',
                   'a4444444-4444-4444-8444-444444444444', :ar, true)
                """
            ),
            {
                "a": str(USER_A),
                "b": str(USER_B),
                "aa": f"{MARKER}_a_active",
                "ba": f"{MARKER}_b_active",
                "ap": f"{MARKER}_a_pending",
                "ar": f"{MARKER}_a_revoked",
            },
        )

        conn.execute(text("GRANT USAGE ON SCHEMA app TO authenticated"))
        conn.execute(
            text(
                """
                GRANT SELECT ON
                  app.agent_decisions,
                  app.system_events,
                  app.strategy_configs,
                  app.exchange_account_bindings
                TO authenticated
                """
            )
        )

        conn.execute(text("SET LOCAL ROLE authenticated"))

        # Prove auth.uid() resolves synthetic identity
        _set_jwt_sub(conn, str(USER_A))
        uid = conn.execute(text("SELECT auth.uid()")).scalar()
        _assert_eq("auth_uid_user_a", str(uid), str(USER_A))

        _assert_eq("A_agent", _count(conn, "SELECT count(*) FROM app.agent_decisions"), 1)
        _assert_eq("A_events", _count(conn, "SELECT count(*) FROM app.system_events"), 1)
        _assert_eq("A_strat", _count(conn, "SELECT count(*) FROM app.strategy_configs"), 1)
        _assert_eq(
            "A_bind",
            _count(conn, "SELECT count(*) FROM app.exchange_account_bindings"),
            1,
        )
        statuses = [
            r[0]
            for r in conn.execute(
                text("SELECT status FROM app.exchange_account_bindings ORDER BY 1")
            )
        ]
        _assert_eq("A_bind_statuses", statuses, ["active"])

        # Cross-user: A's agent id must not be B's
        a_owner = conn.execute(
            text("SELECT owner_user_id::text FROM app.agent_decisions")
        ).scalar()
        _assert_eq("A_agent_owner", a_owner, str(USER_A))

        _set_jwt_sub(conn, str(USER_B))
        uid_b = conn.execute(text("SELECT auth.uid()")).scalar()
        _assert_eq("auth_uid_user_b", str(uid_b), str(USER_B))
        _assert_eq("B_agent", _count(conn, "SELECT count(*) FROM app.agent_decisions"), 1)
        _assert_eq(
            "B_bind",
            _count(conn, "SELECT count(*) FROM app.exchange_account_bindings"),
            1,
        )
        b_owner = conn.execute(
            text("SELECT owner_user_id::text FROM app.agent_decisions")
        ).scalar()
        _assert_eq("B_agent_owner", b_owner, str(USER_B))

        _set_jwt_sub(conn, "")
        # empty sub → auth.uid() null → no owned rows
        _assert_eq(
            "MISS_agent", _count(conn, "SELECT count(*) FROM app.agent_decisions"), 0
        )

        _set_jwt_sub(conn, str(USER_INVALID))
        _assert_eq(
            "INV_agent", _count(conn, "SELECT count(*) FROM app.agent_decisions"), 0
        )
        _assert_eq(
            "INV_bind",
            _count(conn, "SELECT count(*) FROM app.exchange_account_bindings"),
            0,
        )

        conn.execute(text("RESET ROLE"))
        results["assertions"] = "PASS"
        trans.rollback()
        results["tx"] = "rolled_back"
    except Exception:
        try:
            trans.rollback()
        except Exception:
            pass
        raise
    return results


def post_rollback_verify(engine: Engine) -> dict[str, object]:
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        residual = {
            "agent_decisions": _count(
                conn,
                f"SELECT count(*) FROM app.agent_decisions WHERE reason LIKE '{MARKER}%'",
            ),
            "system_events": _count(
                conn,
                f"SELECT count(*) FROM app.system_events WHERE message LIKE '{MARKER}%'",
            ),
            "strategy_configs": _count(
                conn,
                f"SELECT count(*) FROM app.strategy_configs WHERE name LIKE '{MARKER}%'",
            ),
            "bindings": _count(
                conn,
                "SELECT count(*) FROM app.exchange_account_bindings "
                f"WHERE enrollment_attestation LIKE '{MARKER}%'",
            ),
        }
        if any(residual.values()):
            raise RlsProbeError(f"post_rollback_residual_rows:{residual}")
        usage = bool(
            conn.execute(
                text("SELECT has_schema_privilege('authenticated', 'app', 'USAGE')")
            ).scalar()
        )
        selects = {
            t: bool(
                conn.execute(
                    text(
                        "SELECT has_table_privilege('authenticated', 'app.' || :t, 'SELECT')"
                    ),
                    {"t": t},
                ).scalar()
            )
            for t in TABLES
        }
        if usage or any(selects.values()):
            raise RlsProbeError(
                f"post_rollback_unexpected_grants:usage={usage}:select={selects}"
            )
        return {"residual": residual, "grants_cleared": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Transactional RLS isolation probe (dry-run by default)."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run write/SET ROLE probe (requires approval env flags).",
    )
    args = parser.parse_args(argv)

    try:
        identity = _require_identity()
    except RlsProbeError as exc:
        print(f"RLS_PROBE_REJECTED detail={exc}")
        return 2

    print("RLS_PROBE_IDENTITY_OK")
    print(
        f"project_ref={identity.get('project_ref')} host={identity.get('host')} "
        f"pooler={identity.get('pooler_hint')}"
    )

    engine = _connect()
    try:
        with engine.connect() as conn:
            pre = dry_run_preflight(conn)
        print("RLS_PROBE_DRY_RUN_OK")
        print(
            f"alembic={pre['alembic']} set_role={pre['can_set_role_authenticated']} "
            f"bypassrls={pre['current_role_bypassrls']} fix={pre['insert_fix']}"
        )

        if not args.execute:
            print(
                "RLS_PROBE_MODE=dry_run "
                "(pass --execute only after operator approval + Data API gate)"
            )
            return 0

        if not _env_truthy("CRYPTONOVA_APPROVE_TRANSACTIONAL_RLS"):
            print(
                "RLS_PROBE_REJECTED detail=missing_approval:"
                "CRYPTONOVA_APPROVE_TRANSACTIONAL_RLS=yes"
            )
            return 2
        if not _env_truthy("CRYPTONOVA_DATA_API_APP_NOT_EXPOSED"):
            print(
                "RLS_PROBE_REJECTED detail=data_api_gate:"
                "CRYPTONOVA_DATA_API_APP_NOT_EXPOSED=yes required"
            )
            return 2

        # One connection for the entire mutating transaction
        with engine.connect() as conn:
            exec_result = execute_probe(conn)
        print("RLS_PROBE_EXECUTE_ASSERTIONS_OK")
        print(f"tx={exec_result.get('tx')}")

        post = post_rollback_verify(engine)
        print("RLS_PROBE_POST_ROLLBACK_OK")
        print(f"grants_cleared={post['grants_cleared']}")
        print("RLS_PROBE_EXECUTE_PASS")
        return 0
    except RlsProbeError as exc:
        print(f"RLS_PROBE_FAILED detail={exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"RLS_PROBE_FAILED detail={type(exc).__name__}")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
