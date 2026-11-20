"""Arranca um PostgreSQL local persistente (pgserver) e imprime a ligação admin.

Uso:  python scripts/dev_postgres.py
- Dados em .pgdata-dev/ (ignorado pelo git).
- O servidor continua a correr depois de o script terminar (cleanup_mode=None).
- A porta muda quando o servidor reinicia: volte a correr o script e actualize QS_ADMIN_DSN.
- Autenticação local de confiança (trust) apenas em 127.0.0.1; não há password nesta ligação.
"""

from __future__ import annotations

from pathlib import Path

import pgserver
import psycopg

ROOT = Path(__file__).resolve().parent.parent
PGDATA = ROOT / ".pgdata-dev"
DEV_DB = "queryshield"


def main() -> None:
    PGDATA.mkdir(exist_ok=True)
    server = pgserver.get_server(PGDATA, cleanup_mode=None)
    with psycopg.connect(server.get_uri(), autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DEV_DB,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{DEV_DB}"')
    admin_dsn = server.get_uri(database=DEV_DB)
    version = psycopg.connect(admin_dsn).execute("SELECT version()").fetchone()[0]
    print(f"PostgreSQL ativo: {version.split(',')[0]}")
    print(f"QS_ADMIN_DSN={admin_dsn}")
    print("Defina também QS_READER_PASSWORD e QS_READER_DSN (ver README).")


if __name__ == "__main__":
    main()
