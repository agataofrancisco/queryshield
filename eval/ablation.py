"""Experiência de laboratório: o que a BASE DE DADOS trava quando o validador está desligado.

Só para avaliação (nunca exposto pela API). Executa o SQL de ataque TAL COMO ESTÁ, como
instrução de topo, com o role de login do vendedor (qs_reader_s<N>), numa transacção READ ONLY
com o mesmo begin_request que a produção. A transacção é SEMPRE revertida.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg import errors as pg_errors

LAYER_LABELS = {
    pg_errors.SyntaxError: "base de dados: sintaxe",
    pg_errors.InsufficientPrivilege: "base de dados: privilégio",
    pg_errors.ReadOnlySqlTransaction: "base de dados: só leitura",
    pg_errors.QueryCanceled: "base de dados: timeout",
    pg_errors.UndefinedColumn: "base de dados: coluna inexistente",
    pg_errors.UndefinedTable: "base de dados: tabela inexistente",
}


@dataclass(frozen=True)
class RawOutcome:
    layer: str  # "base de dados: ..." | "não bloqueado" | "base de dados: RLS (0 linhas)"
    blocked: bool
    row_count: int
    detail: str


def raw_attempt(seller_dsn: str, sql: str, timeout_ms: int = 3000) -> RawOutcome:
    """Executa sql como instrução de topo na ligação do vendedor e reverte sempre."""
    with psycopg.connect(seller_dsn) as conn:
        try:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SELECT qs_api.begin_request(%s)", (timeout_ms,))
            cursor = conn.execute(sql)
            rows = cursor.fetchall() if cursor.description else []
            if not rows:
                return RawOutcome(
                    "base de dados: RLS (0 linhas)",
                    False,
                    0,
                    "executou sem linhas do outro vendedor",
                )
            return RawOutcome("não bloqueado", False, len(rows), "executou e devolveu linhas")
        except psycopg.Error as exc:
            label = "base de dados: erro"
            for error_type, text in LAYER_LABELS.items():
                if isinstance(exc, error_type):
                    label = text
                    break
            return RawOutcome(label, True, 0, type(exc).__name__)
        finally:
            conn.rollback()
