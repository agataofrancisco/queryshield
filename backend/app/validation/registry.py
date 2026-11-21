"""Registo, por utilizador, dos hashes de SQL que passaram na validação.

Em memória e limitado em tamanho: é um registo de processo (não sobrevive a reinícios e não
é partilhado entre instâncias). A execução confirma sempre o SQL de novo; o registo serve para
o cliente provar que o SQL não mudou desde a validação.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

MAX_HASHES_PER_USER = 500


class ValidatedRegistry:
    def __init__(self, max_per_user: int = MAX_HASHES_PER_USER) -> None:
        self._max = max_per_user
        self._data: dict[str, OrderedDict[str, None]] = {}
        self._lock = threading.Lock()

    def add(self, user: str, sql_hash: str) -> None:
        with self._lock:
            bucket = self._data.setdefault(user, OrderedDict())
            bucket[sql_hash] = None
            bucket.move_to_end(sql_hash)
            while len(bucket) > self._max:
                bucket.popitem(last=False)

    def contains(self, user: str, sql_hash: str) -> bool:
        with self._lock:
            return sql_hash in self._data.get(user, {})
