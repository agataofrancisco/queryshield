"""Validador AST: cada ataque da spec é travado com o código esperado (tarefas 3.1 e 3.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.semantic.loader import load_semantic_model
from backend.app.semantic.models import Role
from backend.app.validation.ast_validator import normalize_sql, sql_hash, validate_sql
from backend.app.validation.registry import ValidatedRegistry
from tests.unit.conftest import SEMANTIC_DIR

MODEL = load_semantic_model(Path(SEMANTIC_DIR))
FINANCE = Role.SELLER_FINANCE
ANALYST = Role.SELLER_ANALYST

ATTACKS = [
    ("SELECT 1; DROP TABLE orders", "multiple_statements"),
    ("DROP TABLE orders", "statement_not_allowed"),
    ("UPDATE orders SET status = 'cancelled'", "statement_not_allowed"),
    ("DELETE FROM orders", "statement_not_allowed"),
    ("INSERT INTO orders (id) VALUES (1)", "statement_not_allowed"),
    ("SET ROLE qs_app", "statement_not_allowed"),
    ("EXPLAIN SELECT 1", "statement_not_allowed"),
    ("COPY orders TO '/tmp/x'", "statement_not_allowed"),
    ("WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x", "write_in_cte"),
    ("SELECT * FROM internal_fraud_flags LIMIT 5", "table_not_allowed"),
    ("SELECT * FROM qs_private.orders LIMIT 5", "table_not_allowed"),
    ("SELECT * FROM pg_catalog.pg_user LIMIT 5", "table_not_allowed"),
    ("SELECT pg_sleep(10)", "function_not_allowed"),
    ("SELECT pg_read_file('/etc/passwd') LIMIT 1", "function_not_allowed"),
    ("SELECT lo_import('/etc/passwd') LIMIT 1", "function_not_allowed"),
    ("SELECT set_config('app.seller_id', '2', false) LIMIT 1", "function_not_allowed"),
    ("SELECT current_setting('app.seller_id') LIMIT 1", "function_not_allowed"),
    ("SELECT * FROM generate_series(1, 3) LIMIT 1", "function_not_allowed"),
    ("SELECT * FROM orders CROSS JOIN order_items LIMIT 5", "cartesian_product"),
    ("SELECT * FROM orders o, customers c LIMIT 5", "cartesian_product"),
    (
        "SELECT p.id FROM payouts p JOIN customers c ON p.seller_id = c.seller_id LIMIT 5",
        "join_not_allowed",
    ),
    (
        "SELECT o.id FROM orders o JOIN customers c ON o.customer_id = c.id OR o.id = c.id LIMIT 2",
        "join_not_allowed",
    ),
    ("SELECT id FROM orders", "limit_or_aggregation_required"),
    ("SELECT id FROM orders WHERE ordered_on >= %s LIMIT 2", "positional_parameters_not_allowed"),
    ("SELECT id INTO newt FROM orders LIMIT 1", "forbidden_operation"),
    ("SELECT * FROM orders FOR UPDATE", "forbidden_operation"),
    ("SELEC id FROM orders", "parse_error"),
    ("", "empty_query"),
    ("   ;  ", "empty_query"),
]


def test_missing_named_parameter_is_reported() -> None:
    result = validate_sql(
        "SELECT id FROM orders WHERE ordered_on >= %(s)s LIMIT 2", FINANCE, MODEL, {}
    )
    assert "missing_parameter" in {i.code for i in result.issues}


@pytest.mark.parametrize(("sql", "code"), ATTACKS)
def test_each_attack_is_blocked_with_its_code(sql: str, code: str) -> None:
    params = {"s": "2026-01-01"} if "%(s)s" in sql else None
    result = validate_sql(sql, FINANCE, MODEL, params)
    assert not result.ok
    assert code in {i.code for i in result.issues}, [i.code for i in result.issues]


VALID = [
    "SELECT id, total_amount FROM orders WHERE ordered_on >= %(start)s LIMIT 10",
    "SELECT status, COUNT(DISTINCT id) AS n FROM orders GROUP BY status ORDER BY n DESC LIMIT 10",
    "SELECT DATE_TRUNC('month', ordered_on) AS mes, SUM(total_amount) AS t "
    "FROM orders GROUP BY 1 ORDER BY 1 LIMIT 20",
    "SELECT id FROM orders o WHERE EXISTS (SELECT 1 FROM payments p "
    "WHERE p.order_id = o.id AND p.status = 'captured') LIMIT 5",
    "SELECT id, CASE WHEN status = 'delivered' THEN 'ok' ELSE 'outro' END AS e FROM orders LIMIT 5",
    "SELECT c.city, COUNT(o.id) FROM customers c LEFT JOIN orders o "
    "ON o.customer_id = c.id AND o.status = 'delivered' GROUP BY c.city",
    "SELECT o.id FROM orders o JOIN order_items oi ON oi.order_id = o.id "
    "JOIN products p ON p.id = oi.product_id JOIN categories cat ON cat.id = p.category_id LIMIT 3",
    "(SELECT id FROM orders LIMIT 1) UNION ALL (SELECT id FROM orders LIMIT 1)",
    "SELECT COALESCE(SUM(gross_amount), 0) FROM payouts WHERE period_month >= %(a)s",
    "SELECT id FROM orders LIMIT 5 /* comentário sem efeito */",
    "SELECT id FROM orders LIMIT 5;",
]


@pytest.mark.parametrize("sql", VALID)
def test_valid_read_queries_pass(sql: str) -> None:
    params = {"start": "2026-01-01", "a": "2026-01-01"}
    result = validate_sql(sql, FINANCE, MODEL, params)
    assert result.ok, [i.as_dict() for i in result.issues]
    assert result.sql_hash == sql_hash(normalize_sql(sql))


def test_unknown_column_suggests_the_closest_qualified_name() -> None:
    result = validate_sql("SELECT total_value FROM orders LIMIT 2", FINANCE, MODEL)
    issue = next(i for i in result.issues if i.code == "unknown_column")
    assert issue.suggestion == "orders.total_amount"


def test_qualified_unknown_column_is_rejected_with_suggestion() -> None:
    result = validate_sql("SELECT o.total_value FROM orders o LIMIT 2", FINANCE, MODEL)
    assert "unknown_column" in {i.code for i in result.issues}


def test_analyst_cannot_reference_customer_email() -> None:
    result = validate_sql("SELECT email FROM customers LIMIT 5", ANALYST, MODEL)
    assert not result.ok and "unknown_column" in {i.code for i in result.issues}


def test_analyst_cannot_query_payouts() -> None:
    result = validate_sql("SELECT id FROM payouts LIMIT 5", ANALYST, MODEL)
    assert "table_not_allowed" in {i.code for i in result.issues}


def test_cte_name_is_not_treated_as_a_table() -> None:
    sql = "WITH t AS (SELECT id FROM orders LIMIT 3) SELECT id FROM t LIMIT 3"
    assert validate_sql(sql, FINANCE, MODEL).ok


def test_hash_changes_when_sql_changes() -> None:
    first = validate_sql("SELECT id FROM orders LIMIT 5", FINANCE, MODEL)
    second = validate_sql("SELECT id FROM orders LIMIT 6", FINANCE, MODEL)
    assert first.sql_hash and second.sql_hash and first.sql_hash != second.sql_hash


@pytest.mark.parametrize(
    "hostile",
    [None, 123, ["SELECT 1"], {"sql": "x"}, b"SELECT 1", "x" * 30_000, "\x00SELECT 1", "é" * 5],
)
def test_hostile_or_malformed_input_never_raises(hostile: object) -> None:
    result = validate_sql(hostile, FINANCE, MODEL)
    assert result.ok is False
    assert result.issues


@pytest.mark.parametrize(
    "params",
    [["lista"], {"x; DROP": "a"}, {"ok": ["lista"]}, {f"p{i}": 1 for i in range(60)}],
)
def test_malformed_parameters_are_rejected_without_raising(params: object) -> None:
    result = validate_sql("SELECT id FROM orders LIMIT 1", FINANCE, MODEL, params)  # type: ignore[arg-type]
    assert not result.ok


# --- endpoint /query/validate and registry --------------------------------------------------


def _token(client: TestClient, persona: str) -> str:
    return client.post("/auth/demo-login", json={"persona": persona}).json()["access_token"]


def test_validate_endpoint_requires_authentication(client: TestClient) -> None:
    response = client.post("/query/validate", json={"sql": "SELECT id FROM orders LIMIT 1"})
    assert response.status_code == 401


def test_validate_endpoint_registers_only_valid_hashes(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {_token(client, 'financas.ngola')}"}
    good = client.post(
        "/query/validate", headers=headers, json={"sql": "SELECT id FROM orders LIMIT 1"}
    ).json()
    bad = client.post("/query/validate", headers=headers, json={"sql": "DROP TABLE orders"}).json()
    assert good["ok"] is True and good["tables_used"] == ["orders"]
    assert bad["ok"] is False and bad["issues"][0]["code"] == "statement_not_allowed"
    registry = client.app.state.validated  # type: ignore[attr-defined]
    assert registry.contains("financas.ngola", good["sql_hash"])
    assert not registry.contains("financas.ngola", bad["sql_hash"] or "x")


def test_validate_endpoint_rejects_extra_fields_and_oversized_sql(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {_token(client, 'financas.ngola')}"}
    extra = client.post(
        "/query/validate", headers=headers, json={"sql": "SELECT 1", "seller_id": 2}
    )
    assert extra.status_code == 422
    huge = client.post("/query/validate", headers=headers, json={"sql": "x" * 20_001})
    assert huge.status_code == 422


def test_registry_is_isolated_per_user_and_bounded() -> None:
    registry = ValidatedRegistry(max_per_user=2)
    registry.add("a", "h1")
    registry.add("a", "h2")
    registry.add("a", "h3")
    assert not registry.contains("a", "h1")
    assert registry.contains("a", "h3")
    assert not registry.contains("b", "h3")


def test_union_is_not_a_set_node_so_forbidden_check_stays_exact() -> None:
    from sqlglot import exp

    assert not issubclass(exp.Union, exp.Set)


def test_comma_join_with_where_is_refused_on_purpose() -> None:
    sql = "SELECT o.id FROM orders o, customers c WHERE o.customer_id = c.id LIMIT 3"
    result = validate_sql(sql, FINANCE, MODEL)
    assert "cartesian_product" in {i.code for i in result.issues}
