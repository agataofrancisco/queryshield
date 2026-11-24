"""Executor: uma pool por role de vendedor (qs_reader_s<N>), sempre READ ONLY.

Identidade = role. Cada QueryExecutor liga-se com as credenciais de UM vendedor, por isso a
visibilidade é decidida pela base de dados (RLS sobre current_user), não pelo SQL.

Por pedido, numa transacção própria:
  SET TRANSACTION READ ONLY                       (antes de qualquer consulta)
  SELECT qs_api.begin_request(<timeout_ms>)       (statement_timeout local à transacção)
  SELECT * FROM (<sql validado>) AS qs_result LIMIT <max_rows + 1>
com um prazo da aplicação (DeadlineGuard) como segunda camada contra timeouts levantados pelo SQL.

Os erros são traduzidos para códigos genéricos; a mensagem do driver nunca é devolvida.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import errors as pg_errors
from psycopg_pool import ConnectionPool, PoolClosed, PoolTimeout

from backend.app.config import seller_dsn
from backend.app.execution.deadline import DeadlineGuard
from backend.app.execution.errors import ExecutionError


@dataclass(frozen=True)
class ExecutionResult:
    columns: tuple[str, ...]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: float


def to_jsonable(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


class QueryExecutor:
    """Executor ligado a um único role de vendedor."""

    def __init__(
        self,
        conninfo: str,
        *,
        statement_timeout_ms: int,
        max_rows: int,
        max_result_bytes: int,
        cancel_dsn: str | None = None,
        deadline_ms: int | None = None,
        pool_min: int = 1,
        pool_max: int = 3,
    ) -> None:
        self._timeout_ms = statement_timeout_ms
        self._max_rows = max_rows
        self._max_bytes = max_result_bytes
        # The supplied value is only a switch for the legacy constructor API. Never use its
        # credentials: cancel through the same role that owns this query's backend.
        self._cancel_dsn = conninfo if cancel_dsn else None
        self._deadline_ms = deadline_ms if deadline_ms is not None else statement_timeout_ms + 1000
        self._pool = ConnectionPool(
            conninfo,
            min_size=pool_min,
            max_size=pool_max,
            open=False,
            timeout=5,
            kwargs={"connect_timeout": 5, "application_name": "queryshield"},
        )

    def open(self) -> None:
        self._pool.open(wait=False)

    def close(self) -> None:
        self._pool.close()

    def ping(self) -> bool:
        try:
            with self._pool.connection() as conn, conn.transaction():
                conn.execute("SET TRANSACTION READ ONLY")
                return conn.execute("SELECT 1").fetchone() == (1,)
        except (psycopg.Error, PoolTimeout, PoolClosed):
            return False

    def execute(self, sql: str, parameters: dict[str, Any] | None) -> ExecutionResult:
        """Executa SQL já validado, com no máximo max_rows + 1 linhas para detectar truncagem."""
        wrapped = f"SELECT * FROM (\n{sql}\n) AS qs_result LIMIT {self._max_rows + 1}"
        started = time.perf_counter()
        with self._translate_errors():
            with self._pool.connection() as conn, conn.transaction():
                self._enter_read_only(conn)
                with self._deadline(conn):
                    cursor = conn.execute(wrapped, parameters or None)
                    columns = tuple(d.name for d in (cursor.description or ()))
                    fetched = cursor.fetchall()
        truncated = len(fetched) > self._max_rows
        rows = [[to_jsonable(v) for v in row] for row in fetched[: self._max_rows]]
        if sum(len(str(v)) for row in rows for v in row) > self._max_bytes:
            raise ExecutionError("result_too_large", "O resultado excede o tamanho máximo.")
        return ExecutionResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    def explain(self, sql: str, parameters: dict[str, Any] | None) -> list[str]:
        """EXPLAIN sem ANALYZE: mostra o plano sem executar a consulta."""
        with self._translate_errors():
            with self._pool.connection() as conn, conn.transaction():
                self._enter_read_only(conn)
                cursor = conn.execute(f"EXPLAIN\n{sql}", parameters or None)
                return [str(row[0]) for row in cursor.fetchall()]

    def _enter_read_only(self, conn: psycopg.Connection[Any]) -> None:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SELECT qs_api.begin_request(%s)", (self._timeout_ms,))

    def _deadline(self, conn: psycopg.Connection[Any]) -> Any:
        if self._cancel_dsn is None:
            return _NoDeadline()
        return DeadlineGuard(self._cancel_dsn, conn.info.backend_pid, self._deadline_ms / 1000)

    def _translate_errors(self) -> _ErrorTranslator:
        return _ErrorTranslator()


class _NoDeadline:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None


class SellerExecutors:
    """Um executor (uma pool) por vendedor. O vendedor é o do token; nunca vem do SQL."""

    def __init__(
        self,
        template: str,
        seller_ids: Iterable[int],
        *,
        statement_timeout_ms: int,
        max_rows: int,
        max_result_bytes: int,
        deadline_margin_ms: int,
        seller_passwords: dict[int, str] | None = None,
    ) -> None:
        self._by_seller: dict[int, QueryExecutor] = {}
        for seller_id in seller_ids:
            reader_conninfo = seller_dsn(template, seller_id, seller_passwords)
            self._by_seller[seller_id] = QueryExecutor(
                reader_conninfo,
                statement_timeout_ms=statement_timeout_ms,
                max_rows=max_rows,
                max_result_bytes=max_result_bytes,
                # Same login role as the target session: no admin/superuser cancellation DSN.
                cancel_dsn=reader_conninfo,
                deadline_ms=statement_timeout_ms + deadline_margin_ms,
            )

    def open(self) -> None:
        for executor in self._by_seller.values():
            executor.open()

    def close(self) -> None:
        for executor in self._by_seller.values():
            executor.close()

    def ping(self) -> bool:
        return all(executor.ping() for executor in self._by_seller.values())

    def execute(
        self, sql: str, parameters: dict[str, Any] | None, seller_id: int
    ) -> ExecutionResult:
        return self._for(seller_id).execute(sql, parameters)

    def explain(self, sql: str, parameters: dict[str, Any] | None, seller_id: int) -> list[str]:
        return self._for(seller_id).explain(sql, parameters)

    def _for(self, seller_id: int) -> QueryExecutor:
        executor = self._by_seller.get(seller_id)
        if executor is None:
            raise ExecutionError("permission_denied", "Vendedor sem ligação configurada.")
        return executor


class _ErrorTranslator:
    """Converte excepções do driver em códigos genéricos sem expor detalhes."""

    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> bool:
        if exc is None or isinstance(exc, ExecutionError):
            return False
        raise _translate(exc) from None


def _translate(exc: BaseException) -> ExecutionError:
    if isinstance(exc, (PoolTimeout, PoolClosed)):
        return ExecutionError("database_unavailable", "Base de dados indisponível.")
    if isinstance(exc, pg_errors.QueryCanceled):
        return ExecutionError("query_timeout", "A consulta excedeu o tempo limite.")
    if isinstance(exc, pg_errors.InsufficientPrivilege):
        return ExecutionError("permission_denied", "Sem permissão para esta consulta.")
    if isinstance(exc, pg_errors.ReadOnlySqlTransaction):
        return ExecutionError("read_only_violation", "Escrita recusada: consulta só de leitura.")
    if isinstance(exc, psycopg.OperationalError):
        return ExecutionError("database_unavailable", "Base de dados indisponível.")
    return ExecutionError("execution_failed", "Não foi possível executar a consulta.")
