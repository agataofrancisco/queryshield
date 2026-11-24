"""Executor contra PostgreSQL real, com o VALIDADOR DESLIGADO: a base de dados trava sozinha.

Cada teste simula um SQL gerado que passou (ou contornou) o validador. Tarefa 4.2 e segunda camada
de timeout (prazo da aplicação, achado A7).
"""

from __future__ import annotations

import time

import psycopg
import pytest

from backend.app.execution.deadline import DeadlineGuard
from backend.app.execution.errors import ExecutionError
from backend.app.execution.executor import QueryExecutor, SellerExecutors
from tests.postgres.conftest import PgEnv

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def executor(pg_env: PgEnv):  # type: ignore[no-untyped-def]
    ex = QueryExecutor(
        pg_env.seller_dsn(1), statement_timeout_ms=3000, max_rows=500, max_result_bytes=1_000_000
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


def test_rows_are_limited_to_the_seller_role(pg_env: PgEnv, executor: QueryExecutor) -> None:
    result = executor.execute("SELECT count(*) AS n FROM orders", None)
    assert result.rows == [[_admin_count(pg_env, 1)]]


def test_each_seller_pool_sees_only_its_own_rows(pg_env: PgEnv) -> None:
    sellers = SellerExecutors(
        pg_env.reader_template,
        (1, 2, 3),
        statement_timeout_ms=3000,
        max_rows=500,
        max_result_bytes=1_000_000,
        deadline_margin_ms=1000,
        seller_passwords=pg_env.seller_passwords,
    )
    sellers.open()
    try:
        for seller in (2, 3, 1):
            result = sellers.execute("SELECT count(*) FROM orders", None, seller_id=seller)
            assert result.rows == [[_admin_count(pg_env, seller)]], seller
    finally:
        sellers.close()


def test_unconfigured_seller_is_refused(pg_env: PgEnv) -> None:
    sellers = SellerExecutors(
        pg_env.reader_template,
        (1,),
        statement_timeout_ms=3000,
        max_rows=5,
        max_result_bytes=10_000,
        deadline_margin_ms=1000,
        seller_passwords=pg_env.seller_passwords,
    )
    with pytest.raises(ExecutionError) as info:
        sellers.execute("SELECT 1 AS x", None, seller_id=9)
    assert _code(info) == "permission_denied"


def test_cross_tenant_filter_returns_nothing_without_the_validator(
    executor: QueryExecutor,
) -> None:
    result = executor.execute("SELECT count(*) FROM orders WHERE seller_id = 2", None)
    assert result.rows == [[0]]


def test_write_inside_cte_is_refused_and_changes_nothing(
    pg_env: PgEnv, executor: QueryExecutor
) -> None:
    def cancelled_count() -> int:
        with psycopg.connect(pg_env.admin_dsn) as conn:
            return conn.execute(
                "SELECT count(*) FROM qs_private.orders WHERE status = 'cancelled'"
            ).fetchone()[0]

    before = cancelled_count()
    sql = "WITH x AS (UPDATE orders SET status = 'cancelled' RETURNING id) SELECT * FROM x"
    with pytest.raises(ExecutionError) as info:
        executor.execute(sql, None)
    assert _code(info) in {"read_only_violation", "execution_failed"}
    assert cancelled_count() == before


def test_secret_table_is_refused_by_the_database(executor: QueryExecutor) -> None:
    with pytest.raises(ExecutionError) as info:
        executor.execute("SELECT * FROM qs_private.internal_fraud_flags", None)
    assert _code(info) == "permission_denied"


def test_public_customer_view_has_no_email_column(executor: QueryExecutor) -> None:
    with pytest.raises(ExecutionError) as info:
        executor.execute("SELECT email FROM customers", None)
    assert _code(info) == "execution_failed"


def test_sql_cannot_change_the_visibility_inside_the_transaction(executor: QueryExecutor) -> None:
    with pytest.raises(ExecutionError) as info:
        executor.execute("SELECT set_config('app.seller_id', '2', true) AS x", None)
    assert _code(info) == "permission_denied"


def test_slow_query_is_cancelled_by_statement_timeout(pg_env: PgEnv) -> None:
    fast = QueryExecutor(
        pg_env.seller_dsn(1), statement_timeout_ms=200, max_rows=10, max_result_bytes=100_000
    )
    fast.open()
    try:
        started = time.perf_counter()
        with pytest.raises(ExecutionError) as info:
            fast.execute("SELECT pg_sleep(5) AS s", None)
        assert _code(info) == "query_timeout"
        assert time.perf_counter() - started < 4
    finally:
        fast.close()


def test_application_deadline_cancels_a_query_that_outlives_its_budget(pg_env: PgEnv) -> None:
    """A base de dados aceitaria 10 s; o prazo da aplicação de 0,8 s cancela antes."""
    guarded = QueryExecutor(
        pg_env.seller_dsn(1),
        statement_timeout_ms=10_000,
        max_rows=10,
        max_result_bytes=100_000,
        deadline_ms=800,
    )
    guarded.open()
    try:
        started = time.perf_counter()
        with pytest.raises(ExecutionError) as info:
            guarded.execute("SELECT pg_sleep(5) AS s", None)
        assert _code(info) == "query_timeout"
        assert time.perf_counter() - started < 4
    finally:
        guarded.close()


def test_application_deadline_cancels_a_session_that_raised_its_own_timeout(
    pg_env: PgEnv,
) -> None:
    """SQL da sessão sobe o statement_timeout para 60 s (achado A7). O prazo da aplicação corta."""
    with psycopg.connect(pg_env.seller_dsn(1)) as conn:
        pid = conn.info.backend_pid
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SELECT qs_api.begin_request(3000)")
        conn.execute("SET statement_timeout = '60s'")
        assert conn.execute("SHOW statement_timeout").fetchone() == ("1min",)
        started = time.perf_counter()
        with pytest.raises(psycopg.errors.QueryCanceled):
            with DeadlineGuard(pg_env.seller_dsn(1), pid, 1.0) as guard:
                conn.execute("SELECT pg_sleep(4)")
        assert guard.fired is True
        assert time.perf_counter() - started < 3.5
        conn.rollback()


def test_deadline_does_not_cancel_a_statement_that_already_finished(pg_env: PgEnv) -> None:
    with psycopg.connect(pg_env.seller_dsn(1)) as conn:
        pid = conn.info.backend_pid
        conn.execute("SET TRANSACTION READ ONLY")
        with DeadlineGuard(pg_env.seller_dsn(1), pid, 0.3) as guard:
            assert conn.execute("SELECT 1").fetchone() == (1,)
        time.sleep(0.6)
        assert guard.fired is False
        assert conn.execute("SELECT 2").fetchone() == (2,)
        conn.rollback()


def test_result_is_truncated_at_max_rows(pg_env: PgEnv) -> None:
    small = QueryExecutor(
        pg_env.seller_dsn(1), statement_timeout_ms=3000, max_rows=5, max_result_bytes=1_000_000
    )
    small.open()
    try:
        result = small.execute("SELECT id FROM orders", None)
        assert result.row_count == 5 and result.truncated is True
    finally:
        small.close()


def test_result_size_limit_is_enforced(pg_env: PgEnv) -> None:
    tiny = QueryExecutor(
        pg_env.seller_dsn(1), statement_timeout_ms=3000, max_rows=500, max_result_bytes=100
    )
    tiny.open()
    try:
        with pytest.raises(ExecutionError) as info:
            tiny.execute("SELECT full_name, city FROM customers", None)
        assert _code(info) == "result_too_large"
    finally:
        tiny.close()


def test_values_are_json_safe(executor: QueryExecutor) -> None:
    result = executor.execute(
        "SELECT sum(total_amount) AS total, min(ordered_on) AS first FROM orders", None
    )
    total, first = result.rows[0]
    assert isinstance(total, str)
    assert isinstance(first, str) and len(first) == 10


def test_explain_does_not_execute_the_query(executor: QueryExecutor) -> None:
    started = time.perf_counter()
    plan = executor.explain("SELECT pg_sleep(2) AS s", None)
    assert time.perf_counter() - started < 1.5
    assert plan and not any("actual time" in line for line in plan)


def test_unreachable_database_error_has_no_credentials_or_host() -> None:
    secret = "SEGREDO-DE-TESTE-123"
    broken = QueryExecutor(
        f"postgresql://qs_reader_s1:{secret}@127.0.0.1:1/nao_existe",
        statement_timeout_ms=3000,
        max_rows=10,
        max_result_bytes=100_000,
    )
    broken.open()
    try:
        with pytest.raises(ExecutionError) as info:
            broken.execute("SELECT 1 AS x", None)
        assert _code(info) == "database_unavailable"
        text = info.value.message + info.value.code
        assert secret not in text and "127.0.0.1" not in text and "nao_existe" not in text
        assert broken.ping() is False
    finally:
        broken.close()
