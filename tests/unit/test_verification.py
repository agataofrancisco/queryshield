"""Verificação semântica e explicação (tarefa 5.1): avisos sem bloqueio e não verificado."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.semantic.loader import load_semantic_model
from backend.app.verification.checks import filter_conditions, verify_semantics
from backend.app.verification.explain import build_explanation
from tests.unit.conftest import SEMANTIC_DIR

MODEL = load_semantic_model(Path(SEMANTIC_DIR))

GOLDEN_RECEITA = (
    "SELECT ROUND(SUM(oi.line_total) - SUM(COALESCE(r.refund, 0)), 2) AS receita "
    "FROM orders o JOIN order_items oi ON oi.order_id = o.id "
    "LEFT JOIN (SELECT order_item_id, SUM(refund_amount) AS refund FROM returns "
    "GROUP BY order_item_id) r ON r.order_item_id = oi.id "
    "WHERE o.status IN ('paid', 'shipped', 'delivered') AND o.currency = 'AOA' "
    "AND o.ordered_on >= %(start)s AND o.ordered_on < %(end)s"
)


def _codes(sql: str) -> list[str]:
    return [w["code"] for w in verify_semantics(sql, MODEL)]


def test_correct_revenue_query_has_no_warnings() -> None:
    assert verify_semantics(GOLDEN_RECEITA, MODEL) == []


def test_revenue_without_returns_is_a_metric_mismatch() -> None:
    sql = (
        "SELECT SUM(oi.line_total) FROM orders o JOIN order_items oi ON oi.order_id = o.id "
        "WHERE o.status IN ('paid', 'shipped', 'delivered') AND o.currency = 'AOA'"
    )
    warnings = verify_semantics(sql, MODEL)
    assert [w["code"] for w in warnings] == ["metric_definition_mismatch"]
    assert "returns" in warnings[0]["message"]


def test_revenue_without_status_filter_is_a_metric_mismatch() -> None:
    sql = (
        "SELECT ROUND(SUM(oi.line_total) - SUM(COALESCE(r.refund, 0)), 2) "
        "FROM orders o JOIN order_items oi ON oi.order_id = o.id "
        "LEFT JOIN (SELECT order_item_id, SUM(refund_amount) AS refund FROM returns "
        "GROUP BY order_item_id) r ON r.order_item_id = oi.id "
        "WHERE o.currency = 'AOA'"
    )
    assert "metric_definition_mismatch" in _codes(sql)


def test_sum_of_parent_total_joined_to_children_is_possible_fanout() -> None:
    sql = (
        "SELECT SUM(o.total_amount) FROM orders o "
        "JOIN order_items oi ON oi.order_id = o.id WHERE o.status = 'paid'"
    )
    assert "possible_fanout" in _codes(sql)


def test_count_distinct_is_not_fanout() -> None:
    sql = (
        "SELECT COUNT(DISTINCT o.id) FROM orders o JOIN order_items oi ON oi.order_id = o.id "
        "WHERE o.status IN ('paid', 'shipped', 'delivered') AND o.currency = 'AOA'"
    )
    assert "possible_fanout" not in _codes(sql)


def test_fanout_is_judged_per_query_scope() -> None:
    # returns está dentro da subquery pré-agregada: não é fan-out sobre order_items.
    assert "possible_fanout" not in _codes(GOLDEN_RECEITA)


def test_order_count_without_status_filter_is_flagged() -> None:
    assert "metric_definition_mismatch" in _codes("SELECT COUNT(o.id) FROM orders o")


def test_filter_conditions_are_listed_in_plain_sql() -> None:
    conditions = filter_conditions(GOLDEN_RECEITA)
    assert any("currency" in c for c in conditions)
    assert any("%(start)s" in c for c in conditions)


def test_explanation_carries_assumptions_warnings_and_row_count() -> None:
    explanation = build_explanation(
        sql="SELECT 1 AS x",
        parameters={"start": "2026-03-01"},
        tables=["orders"],
        assumptions=["Sem período indicado."],
        warnings=[{"code": "possible_fanout", "message": "x"}],
        row_count=1,
    )
    assert explanation["assumptions"] == ["Sem período indicado."]
    assert explanation["warnings"][0]["code"] == "possible_fanout"
    assert explanation["row_count"] == 1 and explanation["tables"] == ["orders"]


def _token(client: TestClient, persona: str) -> dict[str, str]:
    body = client.post("/auth/demo-login", json={"persona": persona}).json()
    return {"Authorization": f"Bearer {body['access_token']}"}


def test_validate_endpoint_reports_verified_false_when_warning_present(client: TestClient) -> None:
    body = client.post(
        "/query/validate",
        headers=_token(client, "financas.ngola"),
        json={
            "sql": "SELECT SUM(oi.line_total) FROM orders o "
            "JOIN order_items oi ON oi.order_id = o.id "
            "WHERE o.status = 'paid' AND o.currency = 'AOA' LIMIT 5"
        },
    ).json()
    assert body["ok"] is True
    assert body["verified"] is False
    assert body["warnings"][0]["code"] == "metric_definition_mismatch"


def test_validate_endpoint_reports_verified_true_for_golden_query(client: TestClient) -> None:
    body = client.post(
        "/query/validate",
        headers=_token(client, "financas.ngola"),
        json={"sql": GOLDEN_RECEITA, "parameters": {"start": "2026-03-01", "end": "2026-04-01"}},
    ).json()
    assert body["ok"] is True and body["verified"] is True and body["warnings"] == []
