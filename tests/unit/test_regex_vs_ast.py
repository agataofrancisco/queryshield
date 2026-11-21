"""Porque é que o validador usa AST e não regex: exemplos executáveis (doc 03).

Duas regras textuais ingénuas, avaliadas isoladamente:
  A) "a consulta começa por SELECT"
  B) "não aparece nenhuma palavra de escrita na lista negra"
Cada caso mostra onde cada regra erra e onde o validador AST decide bem.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.app.semantic.loader import load_semantic_model
from backend.app.semantic.models import Role
from backend.app.validation.ast_validator import validate_sql
from tests.unit.conftest import SEMANTIC_DIR

MODEL = load_semantic_model(Path(SEMANTIC_DIR))
FINANCE = Role.SELLER_FINANCE

RULE_A_STARTS_WITH_SELECT = re.compile(r"^\s*select\b", re.IGNORECASE)
RULE_B_BLACKLIST = re.compile(r"\b(drop|delete|update|insert|alter)\b", re.IGNORECASE)


def rule_a(sql: str) -> bool:
    return bool(RULE_A_STARTS_WITH_SELECT.search(sql))


def rule_b(sql: str) -> bool:
    return not RULE_B_BLACKLIST.search(sql)


@pytest.mark.parametrize(
    ("sql", "expect_a", "expect_b", "expect_ast"),
    [
        # A deixa passar um DROP depois do ponto e vírgula (o início é SELECT).
        ("SELECT 1; DROP TABLE orders", True, False, False),
        # B não conhece TRUNCATE: a lista negra deixa passar uma escrita.
        ("SELECT 1; TRUNCATE orders", True, True, False),
        # A bloqueia uma consulta legítima que começa por WITH.
        ("WITH t AS (SELECT id FROM orders LIMIT 3) SELECT id FROM t LIMIT 3", False, True, True),
        # B bloqueia um literal de texto que não é uma instrução (falso positivo).
        ("SELECT 'DROP TABLE' AS aviso FROM orders LIMIT 1", True, False, True),
        # B bloqueia uma palavra que está só num comentário (falso positivo).
        ("SELECT id FROM orders LIMIT 1 /* DROP TABLE orders */", True, False, True),
    ],
)
def test_text_rules_fail_in_both_directions_and_ast_decides(
    sql: str, expect_a: bool, expect_b: bool, expect_ast: bool
) -> None:
    assert rule_a(sql) is expect_a
    assert rule_b(sql) is expect_b
    assert validate_sql(sql, FINANCE, MODEL).ok is expect_ast


def test_write_inside_with_is_missed_by_starts_with_rule() -> None:
    sql = "WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x"
    assert rule_a(sql) is False  # bloqueada, mas por acaso: a regra não sabe porquê
    result = validate_sql(sql, FINANCE, MODEL)
    assert "write_in_cte" in {i.code for i in result.issues}
