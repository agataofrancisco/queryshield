"""Prova, contra PostgreSQL real, das protecções na base de dados (roles, vistas, RLS, read-only).

Cada teste corresponde a uma afirmação de docs/learn/04-roles-grants-views.md e
docs/learn/05-row-level-security.md.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg import errors

from tests.postgres.conftest import PgEnv

pytestmark = pytest.mark.postgres


def set_tenant(conn: psycopg.Connection, seller_id: int | str) -> None:
    conn.execute("SELECT set_config('app.seller_id', %s, true)", (str(seller_id),))


@pytest.fixture()
def reader(pg_env: PgEnv) -> psycopg.Connection:
    conn = psycopg.connect(pg_env.reader_dsn)
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture()
def admin(pg_env: PgEnv) -> psycopg.Connection:
    conn = psycopg.connect(pg_env.admin_dsn)
    yield conn
    conn.rollback()
    conn.close()


def test_reader_is_a_non_superuser_read_only_role(reader: psycopg.Connection) -> None:
    row = reader.execute(
        "SELECT current_user, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user),"
        " (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user)"
    ).fetchone()
    assert row == ("qs_reader", False, False)
    assert reader.execute("SHOW default_transaction_read_only").fetchone() == ("on",)
    assert reader.execute("SHOW search_path").fetchone() == ("qs_api",)


def test_reader_has_no_privileges_on_base_tables_or_secret_table(
    reader: psycopg.Connection,
) -> None:
    with pytest.raises(errors.InsufficientPrivilege):
        with reader.transaction():
            reader.execute("SELECT count(*) FROM qs_private.internal_fraud_flags").fetchone()
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
    assert "email" not in columns and "phone" not in columns


def test_reader_without_tenant_sees_no_rows(reader: psycopg.Connection) -> None:
    with reader.transaction():
        assert reader.execute("SELECT count(*) FROM orders").fetchone() == (0,)
        assert reader.execute("SELECT count(*) FROM sellers").fetchone() == (0,)


def test_reader_sees_only_the_authenticated_tenant(
    pg_env: PgEnv, reader: psycopg.Connection
) -> None:
    with reader.transaction():
        set_tenant(reader, 1)
        seen = reader.execute(
            "SELECT count(*), min(seller_id), max(seller_id) FROM orders"
        ).fetchone()
    with psycopg.connect(pg_env.admin_dsn) as admin_conn:
        expected = admin_conn.execute(
            "SELECT count(*) FROM qs_private.orders WHERE seller_id = 1"
        ).fetchone()
    assert seen == (expected[0], 1, 1)
    assert seen[0] > 0


def test_sql_that_filters_another_tenant_returns_nothing(reader: psycopg.Connection) -> None:
    with reader.transaction():
        set_tenant(reader, 1)
        assert reader.execute("SELECT count(*) FROM orders WHERE seller_id = 2").fetchone() == (0,)
        assert reader.execute("SELECT count(*) FROM customers WHERE seller_id = 3").fetchone() == (
            0,
        )


def test_tenant_does_not_leak_to_the_next_transaction(reader: psycopg.Connection) -> None:
    with reader.transaction():
        set_tenant(reader, 2)
        assert reader.execute("SELECT count(*) FROM orders").fetchone()[0] > 0
    # Mesmo ligação, nova transacção (o que acontece com um pool): tenant já não existe.
    with reader.transaction():
        assert reader.execute("SELECT count(*) FROM orders").fetchone() == (0,)


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
            set_tenant(reader, 1)
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
    # Mesmo que alguém peça READ WRITE, o role não tem privilégios de escrita.
    with pytest.raises(
        (errors.InsufficientPrivilege, errors.ReadOnlySqlTransaction, errors.FeatureNotSupported)
    ):
        with reader.transaction():
            reader.execute("SET TRANSACTION READ WRITE")
            set_tenant(reader, 1)
            reader.execute(statement)


def test_owner_role_is_subject_to_rls_because_of_force(admin: psycopg.Connection) -> None:
    # Superuser contorna RLS; por isso testamos o dono (qs_app), que sem FORCE também contornaria.
    with admin.transaction():
        admin.execute("SET LOCAL ROLE qs_app")
        assert admin.execute("SELECT count(*) FROM qs_private.orders").fetchone() == (0,)
        set_tenant(admin, 3)
        assert admin.execute(
            "SELECT count(DISTINCT seller_id) FROM qs_private.orders"
        ).fetchone() == (1,)


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
        " WHERE n.nspname = 'qs_private' AND c.relkind = 'r' ORDER BY c.relname"
    ).fetchall()
    assert len(rows) == 10
    for name, enabled, forced, policies in rows:
        assert enabled and forced, name
        assert policies == 1, name
