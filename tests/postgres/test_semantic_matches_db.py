"""A semantic layer tem de coincidir, coluna a coluna, com as vistas que o reader vê na base de dados."""

from __future__ import annotations

import psycopg
import pytest

from backend.app.semantic.loader import load_semantic_model
from tests.postgres.conftest import PgEnv
from tests.unit.conftest import SEMANTIC_DIR

pytestmark = pytest.mark.postgres


def test_semantic_tables_and_columns_match_reader_views(pg_env: PgEnv) -> None:
    model = load_semantic_model(SEMANTIC_DIR)
    with psycopg.connect(pg_env.reader_dsn) as conn:
        rows = conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns"
            " WHERE table_schema = 'qs_api'"
        ).fetchall()
    db_view: dict[str, set[str]] = {}
    for table, column in rows:
        db_view.setdefault(table, set()).add(column)
    assert set(db_view) == set(model.tables)
    for name, spec in model.tables.items():
        assert set(spec.columns) == db_view[name], name
    # internal_fraud_flags não existe em nenhum lado da semantic layer nem das vistas.
    assert "internal_fraud_flags" not in db_view
