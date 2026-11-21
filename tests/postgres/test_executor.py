"""Executor contra PostgreSQL real, com o VALIDADOR DESLIGADO.

A base de dados tem de travar sozinha os ataques que passem o validador.

Cada teste simula um SQL gerado que passou (ou contornou) o validador. Tarefa 4.2.
"""

from __future__ import annotations

import time

import psycopg
import pytest

from backend.app.execution.errors import ExecutionError
from backend.app.execution.executor import QueryExecutor
from tests.postgres.conftest import PgEnv

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def executor(pg_env: PgEnv):  # type: ignore[no-untyped-def]
    ex = QueryExecutor(
        pg_env.reader_dsn, statement_timeout_ms=3000, max_rows=500, max_result_bytes=1_000_000
    )
    ex.open()
    yield ex
    ex.close()


def _admin_count(pg_env: PgEnv, seller: int) -> int:
    with psycopg.connect(pg_env.admin_dsn) as conn:
        return conn.execute(
            "SELECT count(*) FROM qs_private.orders WHERE seller_id = %s", (seller,)
        ).fetchone()[0]


def _code(exc_info: pytest.ExceptionInfo[ExecutionError]) -> str:
    return exc_info.value.code


def test_ping_reports_reachable_database(executor: QueryExecutor) -> None:
    assert executor.ping() is True


def test_rows_are_limited_to_the_authenticated_tenant(
    pg_env: PgEnv, executor: QueryExecutor
) -> None:
    result = executor.execute("SELECT count(*) AS n FROM orders", None, seller_id=1)
    assert result.rows == [[_admin_count(pg_env, 1)]]


def test_tenant_is_not_shared_between_consecutive_requests(
    pg_env: PgEnv, executor: QueryExecutor
) -> None:
    first = executor.execute("SELECT count(*) FROM orders", None, seller_id=2)
    second = executor.execute("SELECT count(*) FROM orders", None, seller_id=3)
    assert first.rows[0][0] == _admin_count(pg_env, 2)
    assert second.rows[0][0] == _admin_count(pg_env, 3)


def test_cross_tenant_filter_returns_nothing_without_the_validator(
    executor: QueryExecutor,
) -> None:
    result = executor.execute("SELECT count(*) FROM orders WHERE seller_id = 2", None, seller_id=1)
    assert result.rows == [[0]]


def test_write_inside_cte_is_refused_and_changes_nothing(
    pg_env: PgEnv, executor: QueryExecutor
) -> None:
    """Escrita dentro de WITH: o PostgreSQL recusa (CTE de escrita não pode estar numa subquery)."""

    def cancelled_count() -> int:
        with psycopg.connect(pg_env.admin_dsn) as conn:
            return conn.execute(
                "SELECT count(*) FROM qs_private.orders WHERE status = 'cancelled'"
            ).fetchone()[0]

    before = cancelled_count()
    sql = "WITH x AS (UPDATE orders SET status = 'cancelled' RETURNING id) SELECT * FROM x"
    with pytest.raises(ExecutionError) as info:
        executor.execute(sql, None, seller_id=1)
    assert _code(info) in {"read_only_violation", "execution_failed"}
    assert cancelled_count() == before


def test_secret_table_is_refused_by_the_database(executor: QueryExecutor) -> None:
    with pytest.raises(ExecutionError) as info:
        executor.execute("SELECT * FROM qs_private.internal_fraud_flags", None, seller_id=1)
    assert _code(info) == "permission_denied"


def test_public_customer_view_has_no_email_column(executor: QueryExecutor) -> None:
    with pytest.raises(ExecutionError) as info:
        executor.execute("SELECT email FROM customers", None, seller_id=1)
    assert _code(info) == "execution_failed"


def test_sql_cannot_change_the_tenant_inside_the_transaction(executor: QueryExecutor) -> None:
    with pytest.raises(ExecutionError) as info:
        executor.execute("SELECT set_config('app.seller_id', '2', true) AS x", None, seller_id=1)
    assert _code(info) == "permission_denied"


def test_sql_cannot_start_a_second_request_scope(executor: QueryExecutor) -> None:
    with pytest.raises(ExecutionError) as info:
        executor.execute("SELECT qs_api.begin_request(2, 3000) AS x", None, seller_id=1)
    assert _code(info) == "permission_denied"


def test_slow_query_is_cancelled_by_statement_timeout(pg_env: PgEnv) -> None:
    fast_timeout = QueryExecutor(
        pg_env.reader_dsn, statement_timeout_ms=200, max_rows=10, max_result_bytes=100_000
    )
    fast_timeout.open()
    try:
        started = time.perf_counter()
        with pytest.raises(ExecutionError) as info:
            fast_timeout.execute("SELECT pg_sleep(5) AS s", None, seller_id=1)
        assert _code(info) == "query_timeout"
        assert time.perf_counter() - started < 4
    finally:
        fast_timeout.close()


def test_result_is_truncated_at_max_rows(pg_env: PgEnv) -> None:
    small = QueryExecutor(
        pg_env.reader_dsn, statement_timeout_ms=3000, max_rows=5, max_result_bytes=1_000_000
    )
    small.open()
    try:
        result = small.execute("SELECT id FROM orders", None, seller_id=1)
        assert result.row_count == 5 and result.truncated is True
    finally:
        small.close()


def test_result_size_limit_is_enforced(pg_env: PgEnv) -> None:
    tiny = QueryExecutor(
        pg_env.reader_dsn, statement_timeout_ms=3000, max_rows=500, max_result_bytes=100
    )
    tiny.open()
    try:
        with pytest.raises(ExecutionError) as info:
            tiny.execute("SELECT full_name, city FROM customers", None, seller_id=1)
        assert _code(info) == "result_too_large"
    finally:
        tiny.close()


def test_values_are_json_safe(executor: QueryExecutor) -> None:
    result = executor.execute(
        "SELECT sum(total_amount) AS total, min(ordered_on) AS first FROM orders",
        None,
        seller_id=1,
    )
    total, first = result.rows[0]
    assert isinstance(total, str)  # Decimal -> texto exacto
    assert isinstance(first, str) and len(first) == 10  # date -> ISO


def test_explain_does_not_execute_the_query(executor: QueryExecutor) -> None:
    started = time.perf_counter()
    plan = executor.explain("SELECT pg_sleep(2) AS s", None, seller_id=1)
    assert time.perf_counter() - started < 1.5
    assert plan and not any("actual time" in line for line in plan)


def test_unreachable_database_error_has_no_credentials_or_host() -> None:
    secret = "SEGREDO-DE-TESTE-123"
    broken = QueryExecutor(
        f"postgresql://qs_reader:{secret}@127.0.0.1:1/nao_existe",
        statement_timeout_ms=3000,
        max_rows=10,
        max_result_bytes=100_000,
    )
    broken.open()
    try:
        with pytest.raises(ExecutionError) as info:
            broken.execute("SELECT 1 AS x", None, seller_id=1)
        assert _code(info) == "database_unavailable"
        text = info.value.message + info.value.code
        assert secret not in text and "127.0.0.1" not in text and "nao_existe" not in text
        assert broken.ping() is False
    finally:
        broken.close()
