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

from backend.app.config import seller_dsn
from db.migrate import apply_migrations
from db.seed import load_seed

# Passwords de TESTE dos roles. Não são segredos: o servidor é local e descartável.
TEST_READER_PASSWORDS = {
    1: "test-only-seller-one-password-24",
    2: "test-only-seller-two-password-24",
    3: "test-only-seller-three-password-24",
}
TEST_DB = "qs_test"


@dataclass(frozen=True)
class PgEnv:
    admin_dsn: str
    reader_template: str
    seller_passwords: dict[int, str]
    server: object
    counts: dict[str, int]

    def seller_dsn(self, seller_id: int) -> str:
        """Ligação do role de login do vendedor (qs_reader_s<N>)."""
        return seller_dsn(self.reader_template, seller_id, self.seller_passwords)

    @property
    def reader_dsn(self) -> str:
        return self.seller_dsn(1)

    def base_uri(self, database: str) -> str:
        return self.server.get_uri(database=database)  # type: ignore[attr-defined]


def reader_template_from_admin(admin_dsn: str) -> str:
    parts = urlsplit(admin_dsn)
    return parts._replace(netloc=f"{{role}}:{{password}}@{parts.hostname}:{parts.port}").geturl()


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
    apply_migrations(admin_dsn, TEST_READER_PASSWORDS)
    counts = load_seed(admin_dsn)
    yield PgEnv(
        admin_dsn=admin_dsn,
        reader_template=reader_template_from_admin(admin_dsn),
        seller_passwords=TEST_READER_PASSWORDS,
        server=server,
        counts=counts,
    )
    server.cleanup()  # type: ignore[attr-defined]
