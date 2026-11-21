"""Histórico por utilizador: pergunta, SQL, estado e avisos. Nunca guarda linhas de resultado.

Em memória e limitado: é um registo de processo. Cada utilizador só lê as suas entradas.
"""

from __future__ import annotations

import threading
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

MAX_ENTRIES_PER_USER = 200


class HistoryStore:
    def __init__(self, max_per_user: int = MAX_ENTRIES_PER_USER) -> None:
        self._max = max_per_user
        self._data: dict[str, deque[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def record(
        self,
        user: str,
        *,
        question: str | None,
        sql: str | None,
        status: str,
        warnings: list[str] | None = None,
        row_count: int | None = None,
    ) -> dict[str, Any]:
        entry = {
            "id": uuid.uuid4().hex,
            "question": question,
            "sql": sql,
            "status": status,
            "warnings": list(warnings or []),
            "row_count": row_count,
            "created_at": datetime.now(UTC).isoformat(),
        }
        with self._lock:
            bucket = self._data.setdefault(user, deque(maxlen=self._max))
            bucket.append(entry)
        return entry

    def list_for(self, user: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in reversed(self._data.get(user, ()))]
