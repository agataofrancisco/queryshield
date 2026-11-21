"""Política estática do validador: nós proibidos, funções permitidas e limites.

Os nomes das classes sqlglot são resolvidos com getattr: uma classe que não exista nesta versão
é simplesmente ignorada (e os testes de validação falham se uma proibição importante desaparecer).
"""

from __future__ import annotations

from sqlglot import exp


def _classes(*names: str) -> frozenset[type[exp.Expression]]:
    found = []
    for name in names:
        cls = getattr(exp, name, None)
        if isinstance(cls, type) and issubclass(cls, exp.Expression):
            found.append(cls)
    return frozenset(found)


# Qualquer nó destes numa consulta é recusado. Dentro de um CTE é classificado como write_in_cte.
FORBIDDEN_NODES: frozenset[type[exp.Expression]] = _classes(
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Create",
    "Drop",
    "Alter",
    "Command",
    "Transaction",
    "Commit",
    "Rollback",
    "Set",
    "SetItem",
    "Copy",
    "Into",
    "Lock",
    "Grant",
    "Use",
    "TruncateTable",
    "Pragma",
    "Execute",
    "Analyze",
    "Show",
    "Describe",
    "Kill",
    "Cache",
    "Refresh",
    "Install",
    "Load",
    "Vacuum",
)

# Operadores e construções sintácticas: são Func em sqlglot, mas não são funções chamáveis.
OPERATOR_NODES: frozenset[type[exp.Expression]] = _classes(
    "And",
    "Or",
    "Not",
    "EQ",
    "NEQ",
    "GT",
    "GTE",
    "LT",
    "LTE",
    "Like",
    "ILike",
    "In",
    "Between",
    "Is",
    "Add",
    "Sub",
    "Mul",
    "Div",
    "Mod",
    "Neg",
    "DPipe",
    "Null",
    "Paren",
    "Case",
    "If",
    "Exists",
    "Distinct",
    "Boolean",
    "Literal",
    "Tuple",
    "Array",
    "Bracket",
    "Escape",
    "Cast",
    "TryCast",
    "Dot",
    "Extract",
    "Interval",
)

# Funções de agregação e escalares com efeitos nulos. Tudo o resto é recusado.
ALLOWED_FUNCTIONS: frozenset[type[exp.Expression]] = _classes(
    "Count",
    "Sum",
    "Avg",
    "Min",
    "Max",
    "Coalesce",
    "Round",
    "Abs",
    "Lower",
    "Upper",
    "Length",
    "Greatest",
    "Least",
    "Nullif",
    "Concat",
    "TimestampTrunc",
    "DateTrunc",
    "CurrentDate",
    "CurrentTimestamp",
    "Substring",
    "Trim",
)

# Funções perigosas conhecidas: mensagem específica, mas a regra real é deny-by-default.
DENIED_FUNCTION_NAMES: frozenset[str] = frozenset(
    {
        "pg_sleep",
        "pg_sleep_for",
        "pg_sleep_until",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "dblink",
        "dblink_exec",
        "lo_import",
        "lo_export",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "set_config",
        "current_setting",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "nextval",
        "setval",
        "copy_to",
        "query_to_xml",
    }
)

MAX_SQL_LENGTH = 20_000
MAX_JOINS = 5
MAX_PARAMETERS = 50
