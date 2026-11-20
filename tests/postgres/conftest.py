"""Fixtures de PostgreSQL real (pgserver) para os testes marcados com `postgres`.

Cada sessão de pytest arranca um servidor PostgreSQL temporário num directório temporário,
cria a base `qs_test`, aplica as migrações e carrega o seed. No fim, o servidor é parado
e o directório apagado. Nenhum teste depende de SQLite.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import urlsplit

import pgserver
import psycopg
import pytest

from db.migrate import apply_migrations
from db.seed import load_seed

# Password de TESTE do role qs_reader. Não é segredo: o servidor é local e descartável.
TEST_READER_PASSWORD = "test-only-reader-password"
TEST_DB = "qs_test"


@dataclass(frozen=True)
class PgEnv:
    admin_dsn: str
    reader_dsn: str
    server: object
    counts: dict[str, int]

    def base_uri(self, database: str) -> str:
        return self.server.get_uri(database=database)  # type: ignore[attr-defined]


def reader_dsn_from_admin(admin_dsn: str, password: str = TEST_READER_PASSWORD) -> str:
    parts = urlsplit(admin_dsn)
    return parts._replace(netloc=f"qs_reader:{password}@{parts.hostname}:{parts.port}").geturl()


def create_database(server: object, name: str) -> None:
    with psycopg.connect(server.get_uri(), autocommit=True) as conn:  # type: ignore[attr-defined]
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}"')


@pytest.fixture(scope="session")
def pg_env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[PgEnv]:
    pgdata = tmp_path_factory.mktemp("pgdata")
    server = pgserver.get_server(pgdata, cleanup_mode="delete")
    create_database(server, TEST_DB)
    admin_dsn = server.get_uri(database=TEST_DB)  # type: ignore[attr-defined]
    apply_migrations(admin_dsn, TEST_READER_PASSWORD)
    counts = load_seed(admin_dsn)
    yield PgEnv(
        admin_dsn=admin_dsn,
        reader_dsn=reader_dsn_from_admin(admin_dsn),
        server=server,
        counts=counts,
    )
    server.cleanup()  # type: ignore[attr-defined]
