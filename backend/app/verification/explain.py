"""Explicação ao utilizador: SQL, filtros, tabelas, parâmetros, suposições e avisos."""

from __future__ import annotations

from typing import Any

from backend.app.verification.checks import filter_conditions


def build_explanation(
    *,
    sql: str,
    parameters: dict[str, Any] | None,
    tables: list[str],
    assumptions: list[str],
    warnings: list[dict[str, str]],
    row_count: int | None = None,
) -> dict[str, Any]:
    return {
        "sql": sql,
        "filters": filter_conditions(sql),
        "parameters": dict(parameters or {}),
        "tables": list(tables),
        "assumptions": list(assumptions),
        "warnings": list(warnings),
        "row_count": row_count,
    }
