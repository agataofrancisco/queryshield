"""Prova, contra PostgreSQL real, do isolamento por vendedor imposto pela base de dados.

A identidade é o role de login: qs_reader_s<N>. A RLS compara seller_id com o vendedor de
current_user (qs_private.seller_roles). Nenhum SQL da sessão muda current_user sem membership,
por isso SET, SET ROLE, RESET ROLE e SET SESSION AUTHORIZATION não mudam o que se vê (achado A1/A2).
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg import errors

from tests.postgres.conftest import PgEnv

pytestmark = pytest.mark.postgres

SELLER_ROLES = ("qs_reader_s1", "qs_reader_s2", "qs_reader_s3")


@pytest.fixture()
def reader(pg_env: PgEnv) -> psycopg.Connection:
    conn = psycopg.connect(pg_env.seller_dsn(1))
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture()
def admin(pg_env: PgEnv) -> psycopg.Connection:
    conn = psycopg.connect(pg_env.admin_dsn)
    yield conn
    conn.rollback()
    conn.close()


def visibility(conn: psycopg.Connection) -> tuple[int, int | None, int | None]:
    return conn.execute("SELECT count(*), min(seller_id), max(seller_id) FROM orders").fetchone()


def test_seller_roles_are_login_roles_that_inherit_nothing(admin: psycopg.Connection) -> None:
    for role in SELLER_ROLES:
        row = admin.execute(
            "SELECT rolcanlogin, rolsuper, rolbypassrls, rolinherit"
            " FROM pg_roles WHERE rolname = %s",
            (role,),
        ).fetchone()
        assert row == (True, False, False, False), role
    memberships = admin.execute(
        "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member"
        " WHERE r.rolname LIKE 'qs_reader_s%%'"
    ).fetchone()
    assert memberships == (0,)


def test_reader_is_read_only_by_default_and_uses_the_views(reader: psycopg.Connection) -> None:
    assert reader.execute("SELECT current_user").fetchone() == ("qs_reader_s1",)
    assert reader.execute("SHOW default_transaction_read_only").fetchone() == ("on",)
    assert reader.execute("SHOW search_path").fetchone() == ("qs_api",)


def test_seller_sees_only_its_own_rows(pg_env: PgEnv, reader: psycopg.Connection) -> None:
    with psycopg.connect(pg_env.admin_dsn) as admin_conn:
        expected = admin_conn.execute(
            "SELECT count(*) FROM qs_private.orders WHERE seller_id = 1"
        ).fetchone()[0]
    assert visibility(reader) == (expected, 1, 1)
    assert expected > 0


@pytest.mark.parametrize(("role", "seller"), [("qs_reader_s2", 2), ("qs_reader_s3", 3)])
def test_each_seller_role_sees_only_its_own_rows(pg_env: PgEnv, role: str, seller: int) -> None:
    with psycopg.connect(pg_env.seller_dsn(seller)) as conn:
        count, low, high = visibility(conn)
    assert (low, high) == (seller, seller) and count > 0


def test_filter_on_another_seller_returns_nothing(reader: psycopg.Connection) -> None:
    assert reader.execute("SELECT count(*) FROM orders WHERE seller_id = 2").fetchone() == (0,)
    assert reader.execute("SELECT count(*) FROM customers WHERE seller_id = 3").fetchone() == (0,)


def test_secret_table_is_not_readable_by_seller_roles(reader: psycopg.Connection) -> None:
    with pytest.raises(errors.InsufficientPrivilege):
        with reader.transaction():
            reader.execute("SELECT count(*) FROM qs_private.internal_fraud_flags").fetchone()


def test_base_tables_are_not_readable_by_seller_roles(reader: psycopg.Connection) -> None:
    with pytest.raises(errors.InsufficientPrivilege):
        with reader.transaction():
            reader.execute("SELECT count(*) FROM qs_private.orders").fetchone()


def test_secret_table_has_no_public_view(reader: psycopg.Connection) -> None:
    with pytest.raises(errors.UndefinedTable):
        with reader.transaction():
            reader.execute("SELECT count(*) FROM internal_fraud_flags").fetchone()


def test_customers_view_has_no_pii_columns(reader: psycopg.Connection) -> None:
    columns = {
        row[0]
        for row in reader.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'qs_api' AND table_name = 'customers'"
        )
    }
    assert columns == {"id", "seller_id", "full_name", "city", "created_on"}


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO categories (id, seller_id, name) VALUES (9999, 1, 'x')",
        "UPDATE orders SET status = 'cancelled'",
        "DELETE FROM orders",
        "DROP TABLE orders",
        "CREATE TABLE public.qs_should_not_exist (i integer)",
    ],
)
def test_writes_are_refused_in_a_read_only_transaction(
    reader: psycopg.Connection, statement: str
) -> None:
    with pytest.raises(errors.ReadOnlySqlTransaction):
        with reader.transaction():
            reader.execute("SET TRANSACTION READ ONLY")
            reader.execute(statement)


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO categories (id, seller_id, name) VALUES (9999, 1, 'x')",
        "UPDATE orders SET status = 'cancelled'",
        "DELETE FROM orders",
        "CREATE TABLE public.qs_should_not_exist (i integer)",
    ],
)
def test_writes_are_refused_even_when_read_write_is_requested(
    reader: psycopg.Connection, statement: str
) -> None:
    with pytest.raises(
        (errors.InsufficientPrivilege, errors.ReadOnlySqlTransaction, errors.FeatureNotSupported)
    ):
        with reader.transaction():
            reader.execute("SET TRANSACTION READ WRITE")
            reader.execute(statement)


@pytest.mark.parametrize(
    "attack",
    [
        "SET app.seller_id = '2'",
        "SET app.seller_id = '3'",
        "SET ROLE qs_app",
        "SET ROLE qs_reader_s2",
        "RESET ROLE",
        "SET SESSION AUTHORIZATION postgres",
        "SET SESSION AUTHORIZATION DEFAULT",
        "SELECT set_config('app.seller_id', '2', true)",
        "SELECT qs_api.begin_request(10000)",
    ],
)
def test_raw_session_attacks_cannot_change_visibility(
    reader: psycopg.Connection, attack: str
) -> None:
    """Com o validador desligado, nenhum ataque de sessão muda o que o vendedor 1 vê."""
    with reader.transaction():
        try:
            with reader.transaction():  # savepoint: um erro não aborta o resto da transacção
                reader.execute(attack)
        except psycopg.Error:
            pass
        assert visibility(reader)[1:] == (1, 1), attack
        assert reader.execute("SELECT current_user").fetchone() == ("qs_reader_s1",), attack


def test_seller_role_cannot_read_or_write_the_mapping_beyond_select(
    reader: psycopg.Connection,
) -> None:
    assert reader.execute(
        "SELECT seller_id FROM qs_private.seller_roles WHERE role_name = 'qs_reader_s1'"
    ).fetchone() == (1,)
    reader.rollback()  # a leitura acima abriu uma transacção; a escrita começa numa nova
    with pytest.raises(errors.InsufficientPrivilege):
        with reader.transaction():
            reader.execute("SET TRANSACTION READ WRITE")
            reader.execute("UPDATE qs_private.seller_roles SET seller_id = 2")


def test_owner_role_is_subject_to_rls_because_of_force(admin: psycopg.Connection) -> None:
    # Superuser contorna RLS; testamos o dono (qs_app), que sem FORCE também contornaria.
    with admin.transaction():
        admin.execute("SET LOCAL ROLE qs_app")
        assert admin.execute("SELECT count(*) FROM qs_private.orders").fetchone() == (0,)


def test_qs_app_cannot_log_in(pg_env: PgEnv) -> None:
    with psycopg.connect(pg_env.admin_dsn) as admin_conn:
        can_login = admin_conn.execute(
            "SELECT rolcanlogin FROM pg_roles WHERE rolname = 'qs_app'"
        ).fetchone()
    assert can_login == (False,)


def test_every_business_table_has_rls_enabled_and_forced(admin: psycopg.Connection) -> None:
    rows = admin.execute(
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,"
        " (SELECT count(*) FROM pg_policies p WHERE p.schemaname = 'qs_private'"
        "   AND p.tablename = c.relname)"
        " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'qs_private' AND c.relkind = 'r' AND c.relname <> 'seller_roles'"
        " ORDER BY c.relname"
    ).fetchall()
    assert len(rows) == 10
    for name, enabled, forced, policies in rows:
        assert enabled and forced, name
        assert policies == 1, name
