"""Vista da semantic layer por papel: a única parte do schema que o modelo e a API veem."""

from __future__ import annotations

from typing import Any

from backend.app.semantic.loader import SemanticModel
from backend.app.semantic.models import Role


def build_role_view(model: SemanticModel, role: Role) -> dict[str, Any]:
    tables = []
    for table in model.visible_tables(role):
        columns = [
            {"name": c.name, "type": c.type, "description": c.description}
            for c in table.visible_columns(role)
        ]
        tables.append({"name": table.name, "description": table.description, "columns": columns})
    visible = {t["name"] for t in tables}
    joins = [e.as_text() for e in model.joins if e.from_table in visible and e.to_table in visible]
    metrics = [
        {
            "name": m.name,
            "title": m.title,
            "description": m.description,
            "unit": m.unit,
            "canonical_sql": m.canonical_sql,
        }
        for m in model.metrics.values()
    ]
    return {"role": role.value, "version": 1, "metrics": metrics, "tables": tables, "joins": joins}
