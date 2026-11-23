"""Normalização de resultados para comparar execuções (funções puras, sem excepções para dados).

Regras:
  * números (inteiros, decimais e texto numérico) são comparados com 2 casas, arredondamento
    half-up; 8529600 == "8529600.00" == Decimal("8529600");
  * NULL é NULL (não é igual a 0);
  * sem ORDER BY pedido, o resultado é um multiconjunto de linhas (ordem irrelevante);
  * com ORDER BY no golden, a ordem das linhas conta.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

NUMERIC_TEXT = re.compile(r"^-?\d+(\.\d+)?$")
CENT = Decimal("0.01")


def normalize_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
    if isinstance(value, Decimal):
        return value.quantize(CENT, rounding=ROUND_HALF_UP) if value.is_finite() else None
    if isinstance(value, float):
        try:
            return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip()
        if NUMERIC_TEXT.match(text):
            try:
                return Decimal(text).quantize(CENT, rounding=ROUND_HALF_UP)
            except InvalidOperation:
                return value
        return value
    return str(value)


def normalize_rows(rows: Iterable[Sequence[Any]]) -> list[tuple[object, ...]]:
    return [tuple(normalize_value(v) for v in row) for row in rows]


def results_equal(
    expected_rows: Iterable[Sequence[Any]],
    actual_rows: Iterable[Sequence[Any]],
    *,
    ordered: bool,
) -> bool:
    expected = normalize_rows(expected_rows)
    actual = normalize_rows(actual_rows)
    if ordered:
        return expected == actual
    return Counter(expected) == Counter(actual)


def is_ordered_golden(golden_sql: str | None) -> bool:
    """Um golden com ORDER BY define uma ordem; sem ORDER BY, o resultado é multiconjunto."""
    if not isinstance(golden_sql, str):
        return False
    return re.search(r"\bORDER\s+BY\b", golden_sql, re.IGNORECASE) is not None


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Percentil por ordem (nearest-rank). None quando não há valores."""
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    rank = max(1, min(len(ordered), math.ceil(fraction * len(ordered))))
    return ordered[rank - 1]
