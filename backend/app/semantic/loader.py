"""Carrega e valida semantic/schema.yaml e semantic/metrics.yaml.

Falha cedo: referências cruzadas inválidas (join para coluna inexistente, papel desconhecido,
métrica a apontar para coluna que não existe) levantam SemanticConfigError ao arrancar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from backend.app.semantic.models import (
    ColumnSpec,
    JoinEdge,
    MetricSpec,
    Role,
    Signature,
    TableSpec,
)

REF_PATTERN = re.compile(r"^([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)$")


class SemanticConfigError(ValueError):
    """Ficheiro semântico inválido."""


@dataclass(frozen=True)
class SemanticModel:
    tables: dict[str, TableSpec]
    metrics: dict[str, MetricSpec]
    joins: tuple[JoinEdge, ...]

    def visible_tables(self, role: Role) -> list[TableSpec]:
        return [t for t in self.tables.values() if role in t.roles]

    def visible_columns(self, role: Role, table: str) -> dict[str, ColumnSpec]:
        spec = self.tables.get(table)
        if spec is None:
            return {}
        return {c.name: c for c in spec.visible_columns(role)}

    def table_names(self) -> frozenset[str]:
        return frozenset(self.tables)

    def is_join_allowed(self, left: tuple[str, str], right: tuple[str, str]) -> bool:
        wanted = frozenset({left, right})
        return any(edge.key() == wanted for edge in self.joins)

    def edges_involving(self, table: str) -> list[JoinEdge]:
        return [e for e in self.joins if table in (e.from_table, e.to_table)]


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SemanticConfigError(f"ficheiro semântico em falta: {path.name}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SemanticConfigError(f"YAML inválido em {path.name}") from exc
    if not isinstance(data, dict):
        raise SemanticConfigError(f"{path.name} deve ser um mapeamento")
    return data


def _parse_role(raw: object, where: str) -> Role:
    try:
        return Role(raw)
    except ValueError as exc:
        raise SemanticConfigError(f"papel desconhecido em {where}: {raw!r}") from exc


def _parse_tables(raw: dict[str, Any]) -> dict[str, TableSpec]:
    tables: dict[str, TableSpec] = {}
    for tname, tdef in raw.items():
        if not isinstance(tdef, dict) or not isinstance(tdef.get("columns"), dict):
            raise SemanticConfigError(f"tabela {tname!r} sem colunas")
        roles = frozenset(_parse_role(r, f"tabela {tname}") for r in tdef.get("roles", []))
        columns: dict[str, ColumnSpec] = {}
        for cname, cdef in tdef["columns"].items():
            if not isinstance(cdef, dict) or not isinstance(cname, str):
                raise SemanticConfigError(f"coluna inválida em {tname}")
            col_roles = cdef.get("roles")
            columns[cname] = ColumnSpec(
                name=cname,
                type=str(cdef.get("type", "")),
                description=str(cdef.get("description", "")),
                roles=(
                    frozenset(_parse_role(r, f"{tname}.{cname}") for r in col_roles)
                    if col_roles is not None
                    else None
                ),
            )
        tables[tname] = TableSpec(
            name=tname,
            description=str(tdef.get("description", "")),
            roles=roles,
            columns=columns,
        )
    return tables


def _parse_ref(text: object, where: str) -> tuple[str, str]:
    if not isinstance(text, str):
        raise SemanticConfigError(f"referência inválida em {where}")
    match = REF_PATTERN.match(text.strip())
    if not match:
        raise SemanticConfigError(f"referência deve ser tabela.coluna: {text!r} em {where}")
    return match.group(1), match.group(2)


def _parse_joins(raw: list[Any]) -> tuple[JoinEdge, ...]:
    edges: list[JoinEdge] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SemanticConfigError(f"join #{index} inválido")
        left = _parse_ref(item.get("from"), f"join #{index}")
        right = _parse_ref(item.get("to"), f"join #{index}")
        edges.append(
            JoinEdge(from_table=left[0], from_column=left[1], to_table=right[0], to_column=right[1])
        )
    return tuple(edges)


def _parse_metrics(raw: dict[str, Any]) -> dict[str, MetricSpec]:
    metrics: dict[str, MetricSpec] = {}
    for mname, mdef in raw.items():
        if not isinstance(mdef, dict):
            raise SemanticConfigError(f"métrica {mname!r} inválida")
        sig_raw = mdef.get("signature")
        signature = None
        if sig_raw is not None:
            if not isinstance(sig_raw, dict):
                raise SemanticConfigError(f"assinatura inválida em {mname}")
            signature = Signature(
                aggregate=sig_raw.get("aggregate"), column=str(sig_raw.get("column", ""))
            )
        metrics[mname] = MetricSpec(
            name=mname,
            title=str(mdef.get("title", mname)),
            description=str(mdef.get("description", "")),
            unit=str(mdef.get("unit", "")),
            canonical_sql=str(mdef.get("canonical_sql", "")),
            signature=signature,
            requires_tables=tuple(mdef.get("requires_tables", []) or []),
            requires_filter_columns=tuple(mdef.get("requires_filter_columns", []) or []),
            filter_column=mdef.get("filter_column"),
        )
    return metrics


def _check_references(model: SemanticModel) -> None:
    def column_exists(table: str, column: str) -> bool:
        return table in model.tables and column in model.tables[table].columns

    for edge in model.joins:
        for table, column in ((edge.from_table, edge.from_column), (edge.to_table, edge.to_column)):
            if not column_exists(table, column):
                raise SemanticConfigError(f"join aponta para coluna inexistente: {table}.{column}")
    for metric in model.metrics.values():
        refs: list[str] = list(metric.requires_filter_columns)
        if metric.filter_column:
            refs.append(metric.filter_column)
        if metric.signature:
            refs.append(metric.signature.column)
        for ref in refs:
            table, _, column = ref.partition(".")
            if not column_exists(table, column):
                raise SemanticConfigError(f"métrica {metric.name} aponta para {ref} inexistente")
        for table in metric.requires_tables:
            if table not in model.tables:
                raise SemanticConfigError(f"métrica {metric.name} exige tabela inexistente {table}")


def load_semantic_model(directory: Path) -> SemanticModel:
    schema_raw = _load_yaml(directory / "schema.yaml")
    metrics_raw = _load_yaml(directory / "metrics.yaml")
    if schema_raw.get("version") != 1 or metrics_raw.get("version") != 1:
        raise SemanticConfigError("versão semântica não suportada (esperado version: 1)")
    joins_raw = schema_raw.get("joins") or []
    if not isinstance(joins_raw, list):
        raise SemanticConfigError("joins deve ser uma lista")
    try:
        model = SemanticModel(
            tables=_parse_tables(schema_raw.get("tables") or {}),
            metrics=_parse_metrics(metrics_raw.get("metrics") or {}),
            joins=_parse_joins(joins_raw),
        )
    except ValidationError as exc:
        raise SemanticConfigError("definições semânticas inválidas") from exc
    _check_references(model)
    return model
