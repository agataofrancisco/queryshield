"""Aplica as migrações SQL versionadas e define a password do role qs_reader.

Uso (PowerShell ou Git Bash, a partir da raiz do projecto):
    python -m db.migrate

Variáveis: QS_ADMIN_DSN (superuser local) e QS_READER_PASSWORD (obrigatória).
A password nunca é impressa nem escrita em ficheiros.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def read_migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def apply_migrations(admin_dsn: str, reader_password: str) -> list[str]:
    """Aplica as migrações pendentes, por ordem, cada uma numa transacção.

    Devolve os nomes das migrações aplicadas nesta execução.
    """
    if not reader_password:
        raise ValueError("QS_READER_PASSWORD é obrigatória.")
    applied: list[str] = []
    with psycopg.connect(admin_dsn) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS public.qs_schema_migrations ("
            " name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        conn.commit()
        done = {row[0] for row in conn.execute("SELECT name FROM public.qs_schema_migrations")}
        for path in read_migration_files():
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO public.qs_schema_migrations (name) VALUES (%s)", (path.name,)
                )
            applied.append(path.name)
        with conn.transaction():
            conn.execute(
                sql.SQL("ALTER ROLE qs_reader PASSWORD {}").format(sql.Literal(reader_password))
            )
    return applied


def main() -> int:
    admin_dsn = os.environ.get("QS_ADMIN_DSN", "")
    reader_password = os.environ.get("QS_READER_PASSWORD", "")
    if not admin_dsn:
        print("QS_ADMIN_DSN não definido.", file=sys.stderr)
        return 2
    try:
        applied = apply_migrations(admin_dsn, reader_password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except psycopg.Error as exc:
        # Só o tipo de erro: a mensagem do driver pode conter a ligação.
        print(f"Falha na migração: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"Migrações aplicadas: {applied or 'nenhuma (já estavam aplicadas)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
