"""Validador AST de SQL gerado (PostgreSQL), baseado em SQLGlot.

Analisa a árvore sintáctica, nunca o texto: comentários, maiúsculas e strings
não enganam o validador.
Devolve sempre um ValidationResult; nunca lança excepção para entradas não confiáveis.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from backend.app.semantic.loader import SemanticModel
from backend.app.semantic.models import Role
from backend.app.validation.policy import (
    ALLOWED_FUNCTIONS,
    DENIED_FUNCTION_NAMES,
    FORBIDDEN_NODES,
    MAX_JOINS,
    MAX_PARAMETERS,
    MAX_SQL_LENGTH,
    OPERATOR_NODES,
)

PARAM_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    suggestion: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "suggestion": self.suggestion}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    issues: tuple[Issue, ...] = ()
    canonical_sql: str = ""
    sql_hash: str = ""
    tables: tuple[str, ...] = ()
    functions: tuple[str, ...] = ()
    joins: tuple[str, ...] = ()
    parameters: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [i.as_dict() for i in self.issues],
            "sql_hash": self.sql_hash,
            "tables_used": list(self.tables),
            "functions_used": list(self.functions),
            "joins_used": list(self.joins),
            "parameters": list(self.parameters),
        }


def normalize_sql(sql: str) -> str:
    """Remove espaços e ponto e vírgula finais. Não reescreve o SQL."""
    text = sql.strip()
    while text.endswith(";"):
        text = text[:-1].rstrip()
    return text


def sql_hash(canonical_sql: str) -> str:
    return hashlib.sha256(canonical_sql.encode("utf-8")).hexdigest()


def _fail(issues: list[Issue], canonical: str = "") -> ValidationResult:
    return ValidationResult(
        ok=False,
        issues=tuple(issues),
        canonical_sql=canonical,
        sql_hash=sql_hash(canonical) if canonical else "",
    )


def validate_sql(
    sql: object,
    role: Role,
    model: SemanticModel,
    parameters: dict[str, Any] | None = None,
) -> ValidationResult:
    if not isinstance(sql, str):
        return _fail([Issue("invalid_input", "O SQL tem de ser texto.")])
    if len(sql) > MAX_SQL_LENGTH:
        return _fail([Issue("sql_too_long", f"SQL acima de {MAX_SQL_LENGTH} caracteres.")])
    canonical = normalize_sql(sql)
    if not canonical:
        return _fail([Issue("empty_query", "A consulta está vazia.")])
    param_issues, param_names = _check_parameter_values(parameters)
    if param_issues:
        return _fail(param_issues, canonical)

    try:
        statements = [s for s in sqlglot.parse(canonical, read="postgres") if s is not None]
    except SqlglotError:
        return _fail([Issue("parse_error", "O SQL não pôde ser analisado.")], canonical)
    if not statements:
        return _fail([Issue("empty_query", "A consulta está vazia.")], canonical)
    if len(statements) > 1:
        return _fail([Issue("multiple_statements", "Só é permitida uma instrução.")], canonical)

    root = statements[0]
    if not isinstance(root, (exp.Select, exp.Union)):
        name = type(root).__name__
        return _fail(
            [
                Issue(
                    "statement_not_allowed",
                    f"Só são permitidas consultas SELECT (recebido: {name}).",
                )
            ],
            canonical,
        )

    checker = _Checker(root, role, model, param_names, parameters or {})
    issues = checker.run()
    return ValidationResult(
        ok=not issues,
        issues=tuple(issues),
        canonical_sql=canonical,
        sql_hash=sql_hash(canonical),
        tables=tuple(sorted(checker.tables_used)),
        functions=tuple(sorted(set(checker.functions_used))),
        joins=tuple(checker.join_texts),
        parameters=tuple(sorted(checker.named_params)),
    )


def _check_parameter_values(parameters: object) -> tuple[list[Issue], frozenset[str]]:
    if parameters is None:
        return [], frozenset()
    if not isinstance(parameters, dict) or len(parameters) > MAX_PARAMETERS:
        return [Issue("invalid_input", "Parâmetros inválidos.")], frozenset()
    for key, value in parameters.items():
        if not isinstance(key, str) or not PARAM_NAME.match(key):
            return [Issue("invalid_input", "Nome de parâmetro inválido.")], frozenset()
        if value is not None and not isinstance(value, (str, int, float, bool)):
            return [
                Issue("invalid_input", f"Valor de parâmetro não suportado: {key}.")
            ], frozenset()
    return [], frozenset(parameters)


def _and_leaves(node: exp.Expression) -> list[exp.Expression]:
    if isinstance(node, exp.Paren):
        return _and_leaves(node.this)
    if isinstance(node, exp.And):
        return _and_leaves(node.left) + _and_leaves(node.right)
    return [node]


def _has_aggregate(select: exp.Select) -> bool:
    return any(True for projection in select.expressions for _ in projection.find_all(exp.AggFunc))


def _outer_selects(node: exp.Expression) -> list[exp.Select]:
    if isinstance(node, exp.Select):
        return [node]
    if isinstance(node, exp.Union):
        return _outer_selects(node.left) + _outer_selects(node.right)
    return []


class _Checker:
    def __init__(
        self,
        root: exp.Expression,
        role: Role,
        model: SemanticModel,
        param_names: frozenset[str],
        parameters: dict[str, Any],
    ) -> None:
        self.root = root
        self.role = role
        self.model = model
        self.parameters = parameters
        self.issues: list[Issue] = []
        self._seen: set[tuple[str, str]] = set()
        self.visible: dict[str, set[str]] = {
            t.name: {c.name for c in t.visible_columns(role)} for t in model.visible_tables(role)
        }
        self.tables_used: set[str] = set()
        self.functions_used: list[str] = []
        self.join_texts: list[str] = []
        self.named_params: set[str] = set()
        self.cte_names = {c.alias_or_name for c in root.find_all(exp.CTE)}
        self.derived = {s.alias for s in root.find_all(exp.Subquery) if s.alias} | self.cte_names
        self.alias_map: dict[str, str] = {}

    def add(self, code: str, message: str, suggestion: str | None = None) -> None:
        if (code, message) not in self._seen:
            self._seen.add((code, message))
            self.issues.append(Issue(code, message, suggestion))

    def run(self) -> list[Issue]:
        self._check_forbidden()
        self._check_tables()
        self._check_columns()
        self._check_functions()
        self._check_joins()
        self._check_limit_or_aggregation()
        self._check_placeholders()
        return self.issues

    def _check_forbidden(self) -> None:
        for node in self.root.walk():
            if type(node) in FORBIDDEN_NODES:
                name = type(node).__name__
                if node.find_ancestor(exp.CTE) is not None:
                    self.add("write_in_cte", f"Operação de escrita dentro de WITH: {name}.")
                else:
                    self.add("forbidden_operation", f"Construção não permitida: {name}.")

    def _check_tables(self) -> None:
        visible = {t.name for t in self.model.visible_tables(self.role)}
        for table in self.root.find_all(exp.Table):
            name = table.name
            if not name:
                continue  # função de tabela: validada em _check_functions
            if table.args.get("db") or table.args.get("catalog"):
                self.add(
                    "table_not_allowed",
                    f"Tabela qualificada por schema não permitida: {table.sql('postgres')}.",
                )
                continue
            if name in self.cte_names:
                continue
            if name not in visible:
                self.add("table_not_allowed", f"Tabela não permitida para o papel: {name}.")
                continue
            self.tables_used.add(name)
            self.alias_map[table.alias or name] = name
            self.alias_map[name] = name

    def _column_candidates(self) -> dict[str, str]:
        """Mapeia nome de coluna visível -> tabela, para as tabelas da consulta."""
        out: dict[str, str] = {}
        for table in self.tables_used:
            for column in self.visible.get(table, set()):
                out.setdefault(column, table)
        return out

    def _check_columns(self) -> None:
        output_aliases = {a.alias for a in self.root.find_all(exp.Alias) if a.alias}
        candidates = self._column_candidates()
        for col in self.root.find_all(exp.Column):
            name = col.name
            qualifier = col.table
            if qualifier:
                if qualifier in self.derived:
                    continue
                table = self.alias_map.get(qualifier)
                if table is None:
                    self.add(
                        "unknown_table_reference", f"Referência a tabela desconhecida: {qualifier}."
                    )
                    continue
                if name in self.visible.get(table, set()):
                    continue
                self._column_error(name, table)
            else:
                if name in output_aliases or name in candidates:
                    continue
                self._column_error(name, None)

    def _all_columns(self, table: str) -> set[str]:
        spec = self.model.tables.get(table)
        return set(spec.columns) if spec is not None else set()

    def _column_error(self, name: str, table: str | None) -> None:
        if table is not None:
            exists_hidden = name in self._all_columns(table)
            pool = sorted(self.visible.get(table, set()))
            suggestion = _closest(name, pool, prefix=f"{table}.")
            if exists_hidden:
                self.add(
                    "column_not_allowed", f"Coluna não permitida para o papel: {table}.{name}."
                )
            else:
                self.add("unknown_column", f"Coluna inexistente: {table}.{name}.", suggestion)
            return
        hidden_anywhere = any(name in self._all_columns(t) for t in self.tables_used)
        pool_map = self._column_candidates()
        suggestion = _closest(name, sorted(pool_map), prefix=None, owner=pool_map)
        if hidden_anywhere:
            self.add("column_not_allowed", f"Coluna não permitida para o papel: {name}.")
        else:
            self.add("unknown_column", f"Coluna inexistente: {name}.", suggestion)

    def _check_functions(self) -> None:
        for node in self.root.walk():
            if isinstance(node, exp.Anonymous):
                name = node.name.lower()
                self.functions_used.append(name)
                hint = " (função perigosa)" if name in DENIED_FUNCTION_NAMES else ""
                self.add("function_not_allowed", f"Função não permitida: {name}{hint}.")
            elif isinstance(node, exp.Func):
                kind = type(node)
                if kind in OPERATOR_NODES or kind in ALLOWED_FUNCTIONS:
                    if kind in ALLOWED_FUNCTIONS:
                        self.functions_used.append(node.sql_name().lower())
                    continue
                name = node.sql_name().lower()
                self.functions_used.append(name)
                self.add("function_not_allowed", f"Função não permitida: {name}.")

    def _resolve(self, column: exp.Column) -> tuple[str, str] | None:
        qualifier = column.table
        if qualifier and qualifier in self.derived:
            return ("derived", column.name)
        if qualifier:
            table = self.alias_map.get(qualifier)
        else:
            cands = self._column_candidates()
            table = cands.get(column.name)
        return (table, column.name) if table else None

    def _check_joins(self) -> None:
        joins = list(self.root.find_all(exp.Join))
        if len(joins) > MAX_JOINS:
            self.add("too_many_joins", f"Demasiados joins (máximo {MAX_JOINS}).")
        for join in joins:
            kind = str(join.args.get("kind") or "").upper()
            on = join.args.get("on")
            using = join.args.get("using")
            if kind == "CROSS" or (on is None and not using):
                self.add(
                    "cartesian_product",
                    "Join sem condição (CROSS JOIN ou lista de tabelas) não é permitido.",
                )
                continue
            if using or on is None:
                self.add("join_not_allowed", "Join USING não é suportado; use ON com colunas.")
                continue
            self._check_on(on)

    def _check_on(self, on: exp.Expression) -> None:
        column_pairs = 0
        for leaf in _and_leaves(on):
            if (
                isinstance(leaf, exp.EQ)
                and isinstance(leaf.left, exp.Column)
                and isinstance(leaf.right, exp.Column)
            ):
                left = self._resolve(leaf.left)
                right = self._resolve(leaf.right)
                if left is None or right is None:
                    self.add("join_not_allowed", "Condição de join com referência desconhecida.")
                    continue
                if left[0] == "derived" or right[0] == "derived":
                    real = right if left[0] == "derived" else left
                    touches_edge = any(real in edge.key() for edge in self.model.joins)
                    if real[0] == "derived" or not touches_edge:
                        self.add("join_not_allowed", "Join com subquery sem relação permitida.")
                        continue
                    column_pairs += 1
                    self.join_texts.append(f"{real[0]}.{real[1]} (subquery)")
                    continue
                if not self.model.is_join_allowed(left, right):
                    text = f"{left[0]}.{left[1]} = {right[0]}.{right[1]}"
                    self.add("join_not_allowed", f"Join não permitido: {text}.")
                    continue
                column_pairs += 1
                self.join_texts.append(f"{left[0]}.{left[1]} = {right[0]}.{right[1]}")
            elif isinstance(leaf, exp.EQ) and (
                isinstance(leaf.left, (exp.Literal, exp.Placeholder))
                or isinstance(leaf.right, (exp.Literal, exp.Placeholder))
            ):
                continue  # filtro de igualdade com valor, não é join
            else:
                self.add(
                    "join_not_allowed", "Condição de join só pode ser igualdade entre colunas."
                )
        if column_pairs == 0:
            self.add("join_not_allowed", "Join sem igualdade entre colunas permitidas.")

    def _check_limit_or_aggregation(self) -> None:
        for select in _outer_selects(self.root):
            bounded = (
                select.args.get("limit") is not None
                or select.args.get("fetch") is not None
                or select.args.get("group") is not None
                or _has_aggregate(select)
            )
            if not bounded:
                self.add(
                    "limit_or_aggregation_required",
                    "A consulta tem de ter LIMIT ou agregação (GROUP BY ou função de agregação).",
                )

    def _check_placeholders(self) -> None:
        for node in self.root.find_all(exp.Placeholder):
            name = node.name
            if not name or name == "?":
                self.add(
                    "positional_parameters_not_allowed",
                    "Use parâmetros com nome, no formato %(nome)s.",
                )
            else:
                self.named_params.add(name)
        missing = sorted(self.named_params - set(self.parameters))
        if missing:
            self.add("missing_parameter", f"Parâmetros em falta: {', '.join(missing)}.")


def _closest(
    name: str, pool: list[str], *, prefix: str | None, owner: dict[str, str] | None = None
) -> str | None:
    matches = difflib.get_close_matches(name, pool, n=1, cutoff=0.6)
    if not matches:
        return None
    match = matches[0]
    if owner is not None:
        return f"{owner[match]}.{match}"
    return f"{prefix}{match}" if prefix else match
