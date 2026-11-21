"""Executor: única porta para a base de dados, com o role só de leitura qs_reader.

Por pedido, numa transacção própria:
  SET TRANSACTION READ ONLY            (antes de qualquer consulta)
  set_config('app.seller_id', ..., true)        -> tenant, local à transacção (RLS)
  set_config('statement_timeout', ..., true)    -> tempo limite, local à transacção
  SELECT * FROM (<sql validado>) AS qs_result LIMIT <max_rows + 1>

Os erros são traduzidos para códigos genéricos. Nunca se devolve a mensagem do driver,
porque pode conter a ligação, SQL ou valores.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import errors as pg_errors
from psycopg_pool import ConnectionPool, PoolClosed, PoolTimeout

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
    def __init__(
        self,
        conninfo: str,
        *,
        statement_timeout_ms: int,
        max_rows: int,
        max_result_bytes: int,
        pool_min: int = 1,
        pool_max: int = 4,
    ) -> None:
        self._timeout_ms = statement_timeout_ms
        self._max_rows = max_rows
        self._max_bytes = max_result_bytes
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
                self._enter_read_only(conn, seller_id=None)
                return conn.execute("SELECT 1").fetchone() == (1,)
        except (psycopg.Error, PoolTimeout, PoolClosed):
            return False

    def execute(
        self, sql: str, parameters: dict[str, Any] | None, seller_id: int
    ) -> ExecutionResult:
        """Executa SQL já validado, limitado a max_rows + 1 linhas para detectar truncagem."""
        wrapped = f"SELECT * FROM (\n{sql}\n) AS qs_result LIMIT {self._max_rows + 1}"
        started = time.perf_counter()
        with self._guard():
            with self._pool.connection() as conn, conn.transaction():
                self._enter_read_only(conn, seller_id=seller_id)
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

    def explain(self, sql: str, parameters: dict[str, Any] | None, seller_id: int) -> list[str]:
        """EXPLAIN sem ANALYZE: mostra o plano sem executar a consulta."""
        with self._guard():
            with self._pool.connection() as conn, conn.transaction():
                self._enter_read_only(conn, seller_id=seller_id)
                cursor = conn.execute(f"EXPLAIN\n{sql}", parameters or None)
                return [str(row[0]) for row in cursor.fetchall()]

    def _enter_read_only(self, conn: psycopg.Connection[Any], seller_id: int | None) -> None:
        conn.execute("SET TRANSACTION READ ONLY")
        if seller_id is not None:
            # Única forma de definir o tenant e o timeout: uma vez por transacção (migração 005).
            conn.execute("SELECT qs_api.begin_request(%s, %s)", (seller_id, self._timeout_ms))

    def _guard(self) -> _ErrorTranslator:
        return _ErrorTranslator()


class _ErrorTranslator:
    """Converte excepções do driver em códigos genéricos sem expor detalhes."""

    def __enter__(self) -> None:
        return None

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: object
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
    if isinstance(exc, psycopg.Error):
        return ExecutionError("execution_failed", "Não foi possível executar a consulta.")
    return ExecutionError("execution_failed", "Não foi possível executar a consulta.")
