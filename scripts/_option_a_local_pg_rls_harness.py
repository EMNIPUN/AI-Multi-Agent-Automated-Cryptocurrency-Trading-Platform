"""
Disposable localhost PostgreSQL harness for Option A RLS / role validation.

Safety:
  - Refuses any host other than 127.0.0.1 / localhost
  - Never uses DATABASE_URL / Supabase
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text

DEFAULT_URL = "postgresql+psycopg://cryptonova_test@127.0.0.1:55432/postgres"


def _assert_local(url: str) -> None:
    low = url.lower()
    if "127.0.0.1" not in low and "localhost" not in low:
        raise SystemExit("ABORT: harness requires localhost/127.0.0.1 only")
    if "supabase" in low or "pooler" in low:
        raise SystemExit("ABORT: refused remote/Supabase URL")


def _is_loopback(host: str | None) -> bool:
    if host is None:
        return True
    h = host.split("/")[0]
    return h in {"127.0.0.1", "::1", "localhost"}


def main() -> int:
    url = os.environ.get("OPTION_A_LOCAL_PG_URL", DEFAULT_URL)
    _assert_local(url)
    eng = create_engine(url, isolation_level="AUTOCOMMIT", future=True)
    results: list[tuple[str, str]] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        results.append((name, status))
        print(f"[{status}] {name}{(' — ' + detail) if detail else ''}")

    owner_a = uuid.UUID("11111111-1111-1111-1111-111111111111")
    owner_b = uuid.UUID("22222222-2222-2222-2222-222222222222")

    with eng.connect() as c:
        host = c.execute(text("SELECT inet_server_addr()::text")).scalar()
        port = c.execute(text("SELECT inet_server_port()")).scalar()
        ok("localhost_bind", _is_loopback(str(host) if host else None), f"host={host} port={port}")
        # Drop sibling harness DBs first so shared role names can be recreated.
        c.execute(text("DROP DATABASE IF EXISTS cryptonova_63b_auth WITH (FORCE)"))
        c.execute(text("DROP DATABASE IF EXISTS cryptonova_opt_a_rls WITH (FORCE)"))
        c.execute(text("CREATE DATABASE cryptonova_opt_a_rls"))

    db_url = url.rsplit("/", 1)[0] + "/cryptonova_opt_a_rls"
    _assert_local(db_url)
    db = create_engine(db_url, isolation_level="AUTOCOMMIT", future=True)

    with db.connect() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
        c.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
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

        # Privilege grant target role (INHERIT ok on base)
        c.execute(text("DROP ROLE IF EXISTS cn_login_noinherit"))
        c.execute(text("DROP ROLE IF EXISTS cn_base_priv"))
        c.execute(
            text("CREATE ROLE cn_base_priv NOLOGIN NOSUPERUSER NOBYPASSRLS INHERIT")
        )
        # Critical: NOINHERIT on the LOGIN member — must not see base grants
        c.execute(
            text(
                "CREATE ROLE cn_login_noinherit LOGIN PASSWORD 'local-only' NOINHERIT IN ROLE cn_base_priv"
            )
        )
        c.execute(text("GRANT USAGE ON SCHEMA app TO cn_base_priv"))
        c.execute(
            text("GRANT SELECT, INSERT, UPDATE ON app.signal_history TO cn_base_priv")
        )
        c.execute(
            text(
                """
                CREATE POLICY sh_base_select ON app.signal_history
                FOR SELECT TO cn_base_priv
                USING (owner_user_id = auth.uid())
                """
            )
        )
        c.execute(
            text(
                "INSERT INTO app.signal_history(id, owner_user_id, decision_id, note) VALUES (:i,:o,:d,:n)"
            ),
            {"i": str(uuid.uuid4()), "o": str(owner_a), "d": "seed_a", "n": "A"},
        )
        c.execute(
            text(
                "INSERT INTO app.signal_history(id, owner_user_id, decision_id, note) VALUES (:i,:o,:d,:n)"
            ),
            {"i": str(uuid.uuid4()), "o": str(owner_b), "d": "seed_b", "n": "B"},
        )

    noinh = create_engine(
        "postgresql+psycopg://cn_login_noinherit:local-only@127.0.0.1:55432/cryptonova_opt_a_rls",
        future=True,
    )
    try:
        with noinh.connect() as c:
            c.execute(
                text("SELECT set_config('request.jwt.claim.sub', :s, true)"),
                {"s": str(owner_a)},
            )
            c.execute(text("SELECT count(*) FROM app.signal_history")).scalar()
        ok("noinherit_login_denied_without_set_role", False, "unexpected success")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        ok(
            "noinherit_login_denied_without_set_role",
            "permission denied" in msg or "insufficient" in msg,
            type(exc).__name__,
        )

    with db.connect() as c:
        c.execute(text("DROP POLICY IF EXISTS sh_base_select ON app.signal_history"))
        c.execute(text("REVOKE ALL ON TABLE app.signal_history FROM cn_base_priv"))
        c.execute(text("REVOKE ALL ON SCHEMA app FROM cn_base_priv"))
        c.execute(text("DROP ROLE IF EXISTS cn_login_noinherit"))
        c.execute(text("DROP ROLE IF EXISTS cn_base_priv"))

        c.execute(text("DROP ROLE IF EXISTS cryptonova_api_runtime_login"))
        c.execute(text("DROP ROLE IF EXISTS cryptonova_api_runtime"))
        c.execute(text("DROP ROLE IF EXISTS cryptonova_migrator"))

        c.execute(
            text(
                "CREATE ROLE cryptonova_api_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT"
            )
        )
        c.execute(
            text(
                "CREATE ROLE cryptonova_api_runtime_login LOGIN PASSWORD 'local-only' INHERIT IN ROLE cryptonova_api_runtime"
            )
        )
        c.execute(
            text(
                "CREATE ROLE cryptonova_migrator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
            )
        )
        c.execute(text("GRANT USAGE ON SCHEMA app TO cryptonova_api_runtime"))
        c.execute(text("GRANT USAGE ON SCHEMA auth TO cryptonova_api_runtime"))
        c.execute(text("GRANT EXECUTE ON FUNCTION auth.uid() TO cryptonova_api_runtime"))
        c.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE ON app.signal_history TO cryptonova_api_runtime"
            )
        )
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

        attrs = c.execute(
            text(
                """
                SELECT rolsuper, rolbypassrls, rolcanlogin, rolinherit
                FROM pg_roles WHERE rolname='cryptonova_api_runtime'
                """
            )
        ).fetchone()
        ok("runtime_not_superuser", attrs[0] is False)
        ok("runtime_nobypassrls", attrs[1] is False)
        ok("runtime_nologin_base", attrs[2] is False)
        ok("runtime_inherit", attrs[3] is True)

        owner_tbl = c.execute(
            text(
                """
                SELECT pg_get_userbyid(c.relowner)
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='app' AND c.relname='signal_history'
                """
            )
        ).scalar()
        ok(
            "runtime_not_table_owner",
            owner_tbl not in {"cryptonova_api_runtime", "cryptonova_api_runtime_login"},
            f"owner={owner_tbl}",
        )

    login = create_engine(
        "postgresql+psycopg://cryptonova_api_runtime_login:local-only@127.0.0.1:55432/cryptonova_opt_a_rls",
        future=True,
    )

    with login.connect() as c:
        c.execute(
            text("SELECT set_config('request.jwt.claim.sub', :s, true)"),
            {"s": str(owner_a)},
        )
        n = c.execute(text("SELECT count(*) FROM app.signal_history")).scalar()
        ok("owner_a_select_own_only", n == 1, f"count={n}")
        note = c.execute(
            text("SELECT note FROM app.signal_history WHERE decision_id='seed_a'")
        ).scalar()
        ok("owner_a_reads_a", note == "A")
        leak = c.execute(
            text("SELECT count(*) FROM app.signal_history WHERE decision_id='seed_b'")
        ).scalar()
        ok("owner_a_cannot_read_b", leak == 0)

        c.execute(
            text(
                "INSERT INTO app.signal_history(id, owner_user_id, decision_id, note) VALUES (:i,:o,:d,:n)"
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
                    "INSERT INTO app.signal_history(id, owner_user_id, decision_id, note) VALUES (:i,:o,:d,:n)"
                ),
                {
                    "i": str(uuid.uuid4()),
                    "o": str(owner_b),
                    "d": "ins_b_forge",
                    "n": "bad",
                },
            )
            c.commit()
            ok("owner_a_insert_as_b_denied", False, "insert succeeded")
        except Exception as exc:  # noqa: BLE001
            c.rollback()
            ok("owner_a_insert_as_b_denied", True, type(exc).__name__)

    with login.connect() as c:
        c.execute(
            text("SELECT set_config('request.jwt.claim.sub', :s, true)"),
            {"s": str(owner_a)},
        )
        c.execute(
            text("UPDATE app.signal_history SET note='hacked' WHERE decision_id='seed_b'")
        )
        visible = c.execute(
            text("SELECT note FROM app.signal_history WHERE decision_id='seed_b'")
        ).scalar()
        ok("owner_a_cannot_see_or_update_b", visible is None)

    with login.connect() as c:
        c.execute(text("SELECT set_config('request.jwt.claim.sub', '', true)"))
        n = c.execute(text("SELECT count(*) FROM app.signal_history")).scalar()
        ok("missing_sub_select_empty", n == 0, f"count={n}")

    with login.connect() as c:
        try:
            c.execute(text("CREATE TABLE app.should_fail(id int)"))
            ok("runtime_cannot_ddl", False)
        except Exception:
            ok("runtime_cannot_ddl", True)

    with login.connect() as c:
        try:
            c.execute(text("DELETE FROM app.signal_history WHERE decision_id='ins_a'"))
            c.commit()
            ok("runtime_no_delete_grant", False, "delete succeeded")
        except Exception as exc:  # noqa: BLE001
            ok("runtime_no_delete_grant", True, type(exc).__name__)

    with login.connect() as c1:
        c1.execute(
            text("SELECT set_config('request.jwt.claim.sub', :s, true)"),
            {"s": str(owner_a)},
        )
        a_count = c1.execute(text("SELECT count(*) FROM app.signal_history")).scalar()
    with login.connect() as c2:
        c2.execute(
            text("SELECT set_config('request.jwt.claim.sub', :s, true)"),
            {"s": str(owner_b)},
        )
        b_count = c2.execute(text("SELECT count(*) FROM app.signal_history")).scalar()
    ok(
        "sequential_connections_identity_switch",
        a_count >= 1 and b_count == 1,
        f"a={a_count} b={b_count}",
    )

    # Verify seed_b unchanged as table owner
    with db.connect() as c:
        note_b = c.execute(
            text("SELECT note FROM app.signal_history WHERE decision_id='seed_b'")
        ).scalar()
        ok("owner_b_row_intact", note_b == "B", f"note={note_b}")

    fails = [n for n, s in results if s == "FAIL"]
    print(
        "SUMMARY",
        f"passed={sum(1 for _, s in results if s == 'PASS')}",
        f"failed={len(fails)}",
    )
    if fails:
        print("FAILED", fails)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
