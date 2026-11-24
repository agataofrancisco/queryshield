"""Aplica as migrações SQL versionadas e define credenciais dos roles de vendedor.

Uso (PowerShell ou Git Bash, a partir da raiz do projecto):
    python -m db.migrate

Variáveis: QS_ADMIN_DSN e QS_READER_PASSWORD_S1..S3 (segredos independentes).
A password nunca é impressa nem escrita em ficheiros.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
# Roles de login por vendedor (migração 006).
SELLER_ROLES = ("qs_reader_s1", "qs_reader_s2", "qs_reader_s3")


def read_migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def apply_migrations(admin_dsn: str, reader_password: str | dict[int, str]) -> list[str]:
    """Aplica as migrações pendentes, por ordem, cada uma numa transacção.

    Devolve os nomes das migrações aplicadas nesta execução.
    """
    distinct_credentials_required = isinstance(reader_password, dict)
    passwords = (
        reader_password
        if distinct_credentials_required
        else {seller_id: reader_password for seller_id in range(1, 4)}
    )
    if set(passwords) != {1, 2, 3} or any(len(passwords[sid]) < 24 for sid in (1, 2, 3)):
        raise ValueError("defina passwords com pelo menos 24 caracteres para cada vendedor.")
    if distinct_credentials_required and len(set(passwords.values())) != 3:
        raise ValueError("cada role de vendedor tem de usar uma password diferente.")
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
            for seller_id, role in enumerate(SELLER_ROLES, start=1):
                conn.execute(
                    sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(passwords[seller_id])
                    )
                )
    return applied


def main() -> int:
    admin_dsn = os.environ.get("QS_ADMIN_DSN", "")
    passwords = {
        seller_id: os.environ.get(f"QS_READER_PASSWORD_S{seller_id}", "")
        for seller_id in (1, 2, 3)
    }
    if not admin_dsn:
        print("QS_ADMIN_DSN não definido.", file=sys.stderr)
        return 2
    try:
        applied = apply_migrations(admin_dsn, passwords)
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
