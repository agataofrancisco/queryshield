"""Funções de normalização e catálogo da avaliação (tarefas 7.1 e 7.2)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from eval.build_questions import QUESTIONS_PATH, load_questions, render_jsonl
from eval.catalog import build_catalog
from eval.normalize import (
    is_ordered_golden,
    normalize_value,
    percentile,
    results_equal,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (8529600, Decimal("8529600.00")),
        ("8529600.00", Decimal("8529600.00")),
        (" 12.5 ", Decimal("12.50")),
        (Decimal("1.005"), Decimal("1.01")),  # half-up
        (None, None),
        ("2026-03-01", "2026-03-01"),
        ("texto", "texto"),
        (True, True),
    ],
)
def test_values_normalise_to_two_decimals_and_keep_null(raw: object, expected: object) -> None:
    assert normalize_value(raw) == expected


def test_null_is_not_zero() -> None:
    assert normalize_value(None) != normalize_value(0)


def test_row_order_is_irrelevant_without_order_by() -> None:
    golden = [["1.00"], ["2.00"]]
    actual = [["2.00"], ["1.00"]]
    assert results_equal(golden, actual, ordered=False)


def test_row_order_matters_when_golden_has_order_by() -> None:
    golden = [["1.00"], ["2.00"]]
    actual = [["2.00"], ["1.00"]]
    assert not results_equal(golden, actual, ordered=True)


def test_duplicate_rows_are_counted() -> None:
    assert not results_equal([["1"], ["1"]], [["1"]], ordered=False)


def test_null_result_does_not_match_zero_result() -> None:
    assert not results_equal([[None]], [[0]], ordered=False)


def test_numeric_text_and_decimal_match() -> None:
    assert results_equal([["8529600.00"]], [[Decimal("8529600")]], ordered=False)


@pytest.mark.parametrize(
    ("sql", "ordered"),
    [
        ("SELECT 1 ORDER BY 1", True),
        ("select 1 order   by x", True),
        ("SELECT 1 AS x", False),
        (None, False),
    ],
)
def test_ordered_detection(sql: str | None, ordered: bool) -> None:
    assert is_ordered_golden(sql) is ordered


def test_percentile_is_nearest_rank_and_none_when_empty() -> None:
    assert percentile([], 0.5) is None
    assert percentile([1, 2, 3, 4], 0.5) == 2
    assert percentile([1, 2, 3, 4], 0.95) == 4


def test_catalogue_has_at_least_100_questions_and_all_categories() -> None:
    questions = build_catalog()
    assert len(questions) >= 100
    categories = {q.category for q in questions}
    assert {"agregacao_receita", "join_multiplo", "ambigua", "ataque", "injecao"} <= categories


def test_catalogue_contains_all_required_attack_families() -> None:
    attacks = " ".join(str(q.attack_sql) for q in build_catalog() if q.attack_sql)
    for needle in (
        "DROP",
        "UPDATE",
        "internal_fraud_flags",
        "WITH",
        "/*",
        ";",
        "CROSS JOIN",
        "seller_id = 2",
        "pg_sleep",
    ):
        assert needle in attacks, needle


def test_question_file_regeneration_is_identical() -> None:
    assert render_jsonl(build_catalog()) == render_jsonl(build_catalog())
    assert QUESTIONS_PATH.read_text(encoding="utf-8") == render_jsonl(build_catalog())


def test_every_rows_question_has_a_golden_sql_and_valid_seller() -> None:
    for record in load_questions():
        if record["expect"] == "rows" and not record["attack_sql"]:
            assert record["golden_sql"], record["id"]
            assert record["seller_id"] in (1, 2, 3), record["id"]


def test_question_ids_are_unique_in_the_file() -> None:
    ids = [r["id"] for r in load_questions()]
    assert len(ids) == len(set(ids))


def test_eval_files_exist_in_the_repository() -> None:
    eval_dir = Path(QUESTIONS_PATH).parent
    assert (eval_dir / "expected.jsonl").exists()
