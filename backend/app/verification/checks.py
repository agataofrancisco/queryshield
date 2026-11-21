"""Verificação semântica do SQL validado: definição de métricas e fan-out.

Corre DEPOIS da validação AST, sobre SQL já aceite. Não bloqueia: produz avisos e marca o
resultado como não verificado. A heurística pode falhar em SQL complexo; por isso a avaliação
mede falsos positivos e negativos (tarefa 7).
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from backend.app.semantic.loader import SemanticModel
from backend.app.semantic.models import MetricSpec

AGGREGATES: tuple[type[exp.Expression], ...] = (exp.Sum, exp.Count, exp.Avg)
AGG_BY_NAME: dict[str, type[exp.Expression]] = {
    "SUM": exp.Sum,
    "COUNT": exp.Count,
    "AVG": exp.Avg,
}


def _and_leaves(node: exp.Expression) -> list[exp.Expression]:
    if isinstance(node, exp.Paren):
        return _and_leaves(node.this)
    if isinstance(node, exp.And):
        return _and_leaves(node.left) + _and_leaves(node.right)
    return [node]


class _Analysis:
    def __init__(self, sql: str, model: SemanticModel) -> None:
        self.root = sqlglot.parse_one(sql, read="postgres")
        self.model = model
        table_nodes = [t for t in self.root.find_all(exp.Table) if t.name]
        self.tables_used = {t.name for t in table_nodes}
        self.aliases = {(t.alias or t.name): t.name for t in table_nodes}
        self.aliases.update({t.name: t.name for t in table_nodes})

    def resolve(self, column: exp.Column) -> tuple[str, str] | None:
        if column.table:
            table = self.aliases.get(column.table)
            return (table, column.name) if table else None
        owners = []
        for table in self.tables_used:
            spec = self.model.tables.get(table)
            if spec is not None and column.name in spec.columns:
                owners.append(table)
        return (owners[0], column.name) if len(owners) == 1 else None

    def scope_tables(self, select: exp.Expression) -> set[str]:
        return {
            t.name
            for t in select.find_all(exp.Table)
            if t.name and t.find_ancestor(exp.Select) is select
        }

    def where_refs(self) -> set[tuple[str, str]]:
        refs: set[tuple[str, str]] = set()
        for where in self.root.find_all(exp.Where):
            for column in where.find_all(exp.Column):
                resolved = self.resolve(column)
                if resolved:
                    refs.add(resolved)
        return refs

    def aggregate_columns(self, agg: exp.Expression) -> list[tuple[str, str]]:
        resolved = [self.resolve(c) for c in agg.find_all(exp.Column)]
        return [r for r in resolved if r is not None]


def _is_distinct(agg: exp.Expression) -> bool:
    return isinstance(agg.this, exp.Distinct)


def _metric_warnings(analysis: _Analysis, metric: MetricSpec) -> list[dict[str, str]]:
    if metric.signature is None:
        return []
    agg_cls = AGG_BY_NAME[metric.signature.aggregate]
    target = tuple(metric.signature.column.split(".", 1))
    used = any(target in analysis.aggregate_columns(agg) for agg in analysis.root.find_all(agg_cls))
    if not used:
        return []
    missing_tables = [t for t in metric.requires_tables if t not in analysis.tables_used]
    where = analysis.where_refs()
    missing_filters = [
        c for c in metric.requires_filter_columns if tuple(c.split(".", 1)) not in where
    ]
    if not missing_tables and not missing_filters:
        return []
    parts = [f"falta a tabela {t}" for t in missing_tables]
    parts += [f"falta o filtro sobre {c}" for c in missing_filters]
    return [
        {
            "code": "metric_definition_mismatch",
            "message": f"{metric.name}: " + "; ".join(parts) + ".",
        }
    ]


def _fanout_warnings(analysis: _Analysis) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for agg in analysis.root.find_all(exp.Sum, exp.Avg, exp.Count):
        if isinstance(agg, exp.Count) and _is_distinct(agg):
            continue
        scope = agg.find_ancestor(exp.Select)
        if scope is None:
            continue
        in_scope = analysis.scope_tables(scope)
        for table, column in analysis.aggregate_columns(agg):
            children = {
                edge.from_table
                for edge in analysis.model.joins
                if edge.to_table == table
                and edge.from_table in in_scope
                and edge.from_table != table
            }
            if table in in_scope and children:
                warnings.append(
                    {
                        "code": "possible_fanout",
                        "message": (
                            f"{agg.sql_name()} sobre {table}.{column} com join a "
                            f"{', '.join(sorted(children))}: valores podem ser duplicados. "
                            "Pré-agregue o lado N antes de somar."
                        ),
                    }
                )
                break
    return warnings


def verify_semantics(sql: str, model: SemanticModel) -> list[dict[str, str]]:
    """Avisos semânticos para um SQL já validado. Lista vazia = nada a assinalar."""
    analysis = _Analysis(sql, model)
    warnings: list[dict[str, str]] = []
    for metric in model.metrics.values():
        warnings.extend(_metric_warnings(analysis, metric))
    warnings.extend(_fanout_warnings(analysis))
    seen: set[tuple[str, str]] = set()
    unique = []
    for warning in warnings:
        key = (warning["code"], warning["message"])
        if key not in seen:
            seen.add(key)
            unique.append(warning)
    return unique


def filter_conditions(sql: str) -> list[str]:
    """Condições do WHERE da consulta externa, em SQL, para a explicação ao utilizador."""
    root = sqlglot.parse_one(sql, read="postgres")
    where = root.args.get("where")
    if where is None:
        return []
    return [leaf.sql("postgres") for leaf in _and_leaves(where.this)]
