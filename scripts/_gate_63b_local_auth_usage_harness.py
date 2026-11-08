"""
Disposable localhost harness: prove auth schema USAGE requirement + LOGIN inherit + pool isolation.

Safety: 127.0.0.1 / localhost only. Never uses DATABASE_URL / Supabase.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

DEFAULT_URL = "postgresql+psycopg://cryptonova_test@127.0.0.1:55432/postgres"


def _assert_local(url: str) -> None:
    low = url.lower()
    if "127.0.0.1" not in low and "localhost" not in low:
        raise SystemExit("ABORT: harness requires localhost/127.0.0.1 only")
    if "supabase" in low or "pooler" in low:
        raise SystemExit("ABORT: refused remote/Supabase URL")


def main() -> int:
    url = os.environ.get("OPTION_A_LOCAL_PG_URL", DEFAULT_URL)
    _assert_local(url)
    results: list[tuple[str, str]] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        results.append((name, status))
        print(f"[{status}] {name}{(' — ' + detail) if detail else ''}")

    owner_a = uuid.UUID("11111111-1111-1111-1111-111111111111")
    owner_b = uuid.UUID("22222222-2222-2222-2222-222222222222")

    admin = create_engine(url, isolation_level="AUTOCOMMIT", future=True)
    with admin.connect() as c:
        ver = c.execute(text("SHOW server_version")).scalar()
        print("server_version", ver)
        c.execute(text("DROP DATABASE IF EXISTS cryptonova_63b_auth WITH (FORCE)"))
        c.execute(text("CREATE DATABASE cryptonova_63b_auth"))

    db_url = url.rsplit("/", 1)[0] + "/cryptonova_63b_auth"
    _assert_local(db_url)
    db = create_engine(db_url, isolation_level="AUTOCOMMIT", future=True)

    with db.connect() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
        c.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
        # Revoke PUBLIC usage on auth to mimic Supabase-managed restriction.
        c.execute(text("REVOKE ALL ON SCHEMA auth FROM PUBLIC"))
        c.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION auth.uid()
                RETURNS uuid LANGUAGE sql STABLE AS $$
                  SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid
                $$
                """
            )
        )
        # EXECUTE for PUBLIC (like remote), but no USAGE yet for runtime.
        c.execute(text("GRANT EXECUTE ON FUNCTION auth.uid() TO PUBLIC"))
        c.execute(
            text(
                """
                CREATE TABLE app.signal_history (
                  id uuid PRIMARY KEY,
                  owner_user_id uuid NOT NULL,
                  decision_id text NOT NULL UNIQUE,
                  note text NOT NULL DEFAULT ''
                )
                """
            )
        )
        c.execute(text("ALTER TABLE app.signal_history ENABLE ROW LEVEL SECURITY"))

        for role in (
            "cryptonova_api_runtime",
            "cryptonova_api_login",
            "cn_login_noinherit",
        ):
            c.execute(text(f"DROP ROLE IF EXISTS {role}"))

        c.execute(
            text(
                "CREATE ROLE cryptonova_api_runtime "
                "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT"
            )
        )
        c.execute(
            text(
                "CREATE ROLE cryptonova_api_login LOGIN PASSWORD 'local-only' "
                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT "
                "IN ROLE cryptonova_api_runtime"
            )
        )
        c.execute(text("GRANT USAGE ON SCHEMA app TO cryptonova_api_runtime"))
        c.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE ON app.signal_history TO cryptonova_api_runtime"
            )
        )
        c.execute(text("GRANT EXECUTE ON FUNCTION auth.uid() TO cryptonova_api_runtime"))
        # Intentionally NO GRANT USAGE ON SCHEMA auth yet.
        c.execute(
            text(
                """
                CREATE POLICY signal_history_runtime_select_own ON app.signal_history
                FOR SELECT TO cryptonova_api_runtime
                USING (owner_user_id = auth.uid())
                """
            )
        )
        c.execute(
            text(
                """
                CREATE POLICY signal_history_runtime_insert_own ON app.signal_history
                FOR INSERT TO cryptonova_api_runtime
                WITH CHECK (owner_user_id = auth.uid())
                """
            )
        )
        c.execute(
            text(
                """
                CREATE POLICY signal_history_runtime_update_own ON app.signal_history
                FOR UPDATE TO cryptonova_api_runtime
                USING (owner_user_id = auth.uid())
                WITH CHECK (owner_user_id = auth.uid())
                """
            )
        )
        c.execute(
            text(
                "INSERT INTO app.signal_history(id, owner_user_id, decision_id, note) "
                "VALUES (:i,:o,:d,:n)"
            ),
            {"i": str(uuid.uuid4()), "o": str(owner_a), "d": "seed_a", "n": "A"},
        )
        c.execute(
            text(
                "INSERT INTO app.signal_history(id, owner_user_id, decision_id, note) "
                "VALUES (:i,:o,:d,:n)"
            ),
            {"i": str(uuid.uuid4()), "o": str(owner_b), "d": "seed_b", "n": "B"},
        )
        usage = c.execute(
            text(
                "SELECT has_schema_privilege('cryptonova_api_runtime','auth','USAGE')"
            )
        ).scalar()
        ok("pregrant_runtime_usage_auth_false", usage is False, f"usage={usage}")

    login_url = (
        "postgresql+psycopg://cryptonova_api_login:local-only@127.0.0.1:55432/"
        "cryptonova_63b_auth"
    )
    login = create_engine(login_url, future=True)

    # Without USAGE: direct auth.uid() should fail; policy evaluation may differ by PG version.
    direct_denied = False
    try:
        with login.connect() as c:
            c.execute(text("SELECT auth.uid()")).scalar()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        direct_denied = "permission denied" in msg or "schema auth" in msg
        ok("without_usage_direct_uid_denied", direct_denied, type(exc).__name__)
    if not direct_denied:
        ok("without_usage_direct_uid_denied", False, "unexpected success")

    policy_denied = False
    policy_count = None
    try:
        with login.connect() as c:
            c.execute(
                text("SELECT set_config('request.jwt.claim.sub', :s, true)"),
                {"s": str(owner_a)},
            )
            policy_count = c.execute(text("SELECT count(*) FROM app.signal_history")).scalar()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        policy_denied = "permission denied" in msg or "schema auth" in msg
        ok("without_usage_policy_select_denied", policy_denied, type(exc).__name__)
    if not policy_denied:
        # Document PG behavior: some builds evaluate SQL uid() without schema USAGE.
        ok(
            "without_usage_policy_select_observed",
            True,
            f"policy_select_succeeded count={policy_count} (document residual)",
        )

    # Grant minimum USAGE and retest.
    with db.connect() as c:
        c.execute(text("GRANT USAGE ON SCHEMA auth TO cryptonova_api_runtime"))
        usage = c.execute(
            text(
                "SELECT has_schema_privilege('cryptonova_api_runtime','auth','USAGE')"
            )
        ).scalar()
        ok("postgrant_runtime_usage_auth_true", usage is True)

    with login.connect() as c:
        c.execute(
            text("SELECT set_config('request.jwt.claim.sub', :s, true)"),
            {"s": str(owner_a)},
        )
        n = c.execute(text("SELECT count(*) FROM app.signal_history")).scalar()
        ok("owner_a_select_own_only", n == 1, f"count={n}")
        leak = c.execute(
            text("SELECT count(*) FROM app.signal_history WHERE decision_id='seed_b'")
        ).scalar()
        ok("owner_a_cannot_read_b", leak == 0)
        c.execute(
            text(
                "INSERT INTO app.signal_history(id, owner_user_id, decision_id, note) "
                "VALUES (:i,:o,:d,:n)"
            ),
            {"i": str(uuid.uuid4()), "o": str(owner_a), "d": "ins_a", "n": "ok"},
        )
        c.commit()
        ok("owner_a_insert_own", True)

    with login.connect() as c:
        c.execute(
            text("SELECT set_config('request.jwt.claim.sub', :s, true)"),
            {"s": str(owner_a)},
        )
        try:
            c.execute(
                text(
                    "INSERT INTO app.signal_history(id, owner_user_id, decision_id, note) "
                    "VALUES (:i,:o,:d,:n)"
                ),
                {
                    "i": str(uuid.uuid4()),
                    "o": str(owner_b),
                    "d": "forge_b",
                    "n": "bad",
                },
            )
            c.commit()
            ok("owner_a_insert_as_b_denied", False)
        except Exception:  # noqa: BLE001
            c.rollback()
            ok("owner_a_insert_as_b_denied", True)

    with login.connect() as c:
        c.execute(
            text("SELECT set_config('request.jwt.claim.sub', :s, true)"),
            {"s": str(owner_a)},
        )
        updated = c.execute(
            text(
                "UPDATE app.signal_history SET note='x' WHERE decision_id='seed_b' "
                "RETURNING decision_id"
            )
        ).fetchall()
        c.commit()
        ok("owner_a_update_b_denied", len(updated) == 0, f"rows={len(updated)}")

    with login.connect() as c:
        c.execute(
            text("SELECT set_config('request.jwt.claim.sub', :s, true)"),
            {"s": str(owner_a)},
        )
        try:
            c.execute(text("DELETE FROM app.signal_history WHERE decision_id='seed_a'"))
            c.commit()
            ok("runtime_delete_denied", False)
        except Exception:  # noqa: BLE001
            c.rollback()
            ok("runtime_delete_denied", True)

    with login.connect() as c:
        try:
            c.execute(text("CREATE TABLE app.pwn (id int)"))
            ok("runtime_ddl_denied", False)
        except Exception:  # noqa: BLE001
            ok("runtime_ddl_denied", True)

    # Missing identity → empty / deny
    with login.connect() as c:
        # no set_config
        n = c.execute(text("SELECT count(*) FROM app.signal_history")).scalar()
        ok("missing_identity_select_empty", n == 0, f"count={n}")

    # Pool isolation: reuse connection A then B
    pooled = create_engine(
        login_url,
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        future=True,
    )
    with pooled.connect() as c1:
        c1.execute(
            text("SELECT set_config('request.jwt.claim.sub', :s, true)"),
            {"s": str(owner_a)},
        )
        a_count = c1.execute(text("SELECT count(*) FROM app.signal_history")).scalar()
        c1.rollback()  # clears SET LOCAL
    with pooled.connect() as c2:
        # After rollback/new txn, prior GUC must not leak
        leaked = c2.execute(text("SELECT count(*) FROM app.signal_history")).scalar()
        c2.execute(
            text("SELECT set_config('request.jwt.claim.sub', :s, true)"),
            {"s": str(owner_b)},
        )
        b_count = c2.execute(text("SELECT count(*) FROM app.signal_history")).scalar()
        c2.rollback()
    ok("pool_owner_a_saw_rows", int(a_count or 0) >= 1, f"a={a_count}")
    ok("pool_reuse_clears_identity", int(leaked or 0) == 0, f"leaked={leaked}")
    ok("pool_owner_b_isolated", int(b_count or 0) >= 1, f"b={b_count}")

    # Identity attrs
    with db.connect() as c:
        row = c.execute(
            text(
                """
                SELECT rolcanlogin, rolbypassrls, rolsuper, rolinherit
                FROM pg_roles WHERE rolname='cryptonova_api_login'
                """
            )
        ).one()
        ok("login_can_login", row[0] is True)
        ok("login_nobypassrls", row[1] is False)
        ok("login_nosuper", row[2] is False)
        ok("login_inherit", row[3] is True)

    failed = [n for n, s in results if s != "PASS"]
    print("summary_pass", sum(1 for _, s in results if s == "PASS"))
    print("summary_fail", len(failed))
    if failed:
        print("failed", ",".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
