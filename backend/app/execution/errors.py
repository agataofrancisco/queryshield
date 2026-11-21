"""Erro de execução com código genérico. A mensagem nunca contém detalhes de infra ou SQL."""

from __future__ import annotations


class ExecutionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
