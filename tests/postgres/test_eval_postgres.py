"""Avaliação contra PostgreSQL real: regeneração idêntica do golden e ablation sem efeitos."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from eval.ablation import raw_attempt
from eval.build_expected import EXPECTED_PATH, build_expected
from tests.postgres.conftest import PgEnv

pytestmark = pytest.mark.postgres


def test_golden_results_regenerate_identically(pg_env: PgEnv, tmp_path: Path) -> None:
    out = tmp_path / "expected.jsonl"
    count = build_expected(pg_env.reader_dsn, output_path=out)
    assert count == 140
    assert out.read_text(encoding="utf-8") == EXPECTED_PATH.read_text(encoding="utf-8")


def test_raw_attack_cannot_change_data_and_is_rolled_back(pg_env: PgEnv) -> None:
    def cancelled() -> int:
        with psycopg.connect(pg_env.admin_dsn) as conn:
            return conn.execute(
                "SELECT count(*) FROM qs_private.orders WHERE status = 'cancelled'"
            ).fetchone()[0]

    before = cancelled()
    outcome = raw_attempt(pg_env.reader_dsn, "UPDATE orders SET status = 'cancelled'", 1)
    assert outcome.blocked is True
    assert outcome.layer == "base de dados: só leitura"
    assert cancelled() == before


def test_raw_cross_tenant_query_returns_no_rows(pg_env: PgEnv) -> None:
    outcome = raw_attempt(pg_env.reader_dsn, "SELECT id FROM orders WHERE seller_id = 2 LIMIT 5", 1)
    assert outcome.blocked is False and outcome.row_count == 0
    assert outcome.layer == "base de dados: RLS (0 linhas)"


def test_raw_secret_table_is_blocked_by_privilege(pg_env: PgEnv) -> None:
    outcome = raw_attempt(pg_env.reader_dsn, "SELECT * FROM qs_private.internal_fraud_flags", 1)
    assert outcome.blocked is True
    assert outcome.layer == "base de dados: privilégio"
