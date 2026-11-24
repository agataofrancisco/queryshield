"""Prazo da aplicação: segunda camada contra timeouts levantados pelo próprio SQL.

O statement_timeout da base de dados pode ser aumentado por SQL na mesma sessão (achado A7).
Este guarda arma um temporizador para o backend concreto e, se o prazo expirar com a instrução
ainda em curso, cancela-o com pg_cancel_backend usando o mesmo role de vendedor.

Garantias:
  * só cancela se a instrução ainda estiver em curso (um lock impede cancelar a seguinte);
  * não regista nem devolve a ligação nem o erro do driver (falhas do cancelamento são ignoradas
    e o pedido termina pelo próprio timeout da base de dados).
"""

from __future__ import annotations

import threading
from types import TracebackType
from typing import Self

import psycopg


class DeadlineGuard:
    def __init__(self, conninfo: str, backend_pid: int, seconds: float) -> None:
        self._conninfo = conninfo
        self._pid = int(backend_pid)
        self._seconds = float(seconds)
        self._lock = threading.Lock()
        self._done = False
        self._timer: threading.Timer | None = None
        self.fired = False

    def __enter__(self) -> Self:
        self._timer = threading.Timer(self._seconds, self._fire)
        self._timer.daemon = True
        self._timer.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        with self._lock:
            self._done = True
        if self._timer is not None:
            self._timer.cancel()

    def _fire(self) -> None:
        with self._lock:
            if self._done:
                return
            self.fired = True
            try:
                with psycopg.connect(self._conninfo, autocommit=True, connect_timeout=3) as conn:
                    conn.execute("SELECT pg_cancel_backend(%s)", (self._pid,))
            except psycopg.Error:
                # Sem detalhes: o timeout da base de dados continua a ser a barreira seguinte.
                return
