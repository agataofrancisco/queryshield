"""Duas bases carregadas com a mesma seed produzem contagens idênticas (tarefa 1.5)."""

from __future__ import annotations

import psycopg
import pytest

from db.migrate import apply_migrations
from db.seed import load_seed
from tests.postgres.conftest import TEST_READER_PASSWORDS, create_database

pytestmark = pytest.mark.postgres


def test_two_databases_with_same_seed_have_identical_counts(pg_env) -> None:  # type: ignore[no-untyped-def]
    create_database(pg_env.server, "qs_test_repro")
    other_admin = pg_env.server.get_uri(database="qs_test_repro")  # type: ignore[attr-defined]
    apply_migrations(other_admin, TEST_READER_PASSWORDS)
    other_counts = load_seed(other_admin)
    assert other_counts == pg_env.counts
    with psycopg.connect(other_admin) as conn:
        total = conn.execute("SELECT sum(total_amount) FROM qs_private.orders").fetchone()
    with psycopg.connect(pg_env.admin_dsn) as conn:
        expected = conn.execute("SELECT sum(total_amount) FROM qs_private.orders").fetchone()
    assert total == expected
