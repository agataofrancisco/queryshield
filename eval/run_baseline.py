"""Baseline INSEGURA (apenas sandbox offline): geração directa sem protecções, para comparação.

Sem validador, sem RLS (superuser), sem READ ONLY e sem o role qs_reader. Cada ataque corre
numa transacção revertida. O runner só aceita uma base cujo nome contenha "sandbox" e cria-a de
raiz; nunca toca na base de desenvolvimento. Um statement_timeout de 5 s é uma guarda do
runner (para não bloquear a máquina), não uma protecção da baseline; o relatório diz isso.

Limitação (Windows): o pgserver escuta sempre em 127.0.0.1. O runner não abre nenhum socket
próprio; a base de sandbox vive no servidor local, que só aceita ligações de loopback.

Uso: QS_SANDBOX_ADMIN_DSN="<ligação superuser ao servidor>" python -m eval.run_baseline
"""

from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from db.migrate import apply_migrations
from db.seed import load_seed
from eval.build_questions import load_questions

EVAL_DIR = Path(__file__).resolve().parent
REPORTS_DIR = EVAL_DIR / "reports"
SANDBOX_DB = "qs_sandbox_insecure_baseline"
SANDBOX_PASSWORD = "sandbox-only-password"  # só para o role de leitura do sandbox


def _sandbox_admin_dsn(server_dsn: str) -> str:
    """Substitui o nome da base em DSN URI ou keyword pelo nome fixo do sandbox."""
    return make_conninfo(server_dsn, dbname=SANDBOX_DB)


def _require_loopback_dsn(server_dsn: str) -> None:
    """Impede que a operação destrutiva de criação toque num servidor remoto."""
    try:
        options = conninfo_to_dict(server_dsn)
    except (psycopg.Error, ValueError) as exc:
        raise ValueError("QS_SANDBOX_ADMIN_DSN inválido") from exc

    for option in ("host", "hostaddr"):
        raw_hosts = options.get(option, "")
        if not raw_hosts:
            continue
        for host in raw_hosts.split(","):
            host = host.strip().strip("[]").lower()
            if host == "localhost":
                continue
            try:
                if ipaddress.ip_address(host).is_loopback:
                    continue
            except ValueError:
                pass
            raise ValueError("a baseline só pode usar um servidor PostgreSQL de loopback")

    if not options.get("host") and not options.get("hostaddr"):
        raise ValueError("QS_SANDBOX_ADMIN_DSN tem de indicar localhost, 127.0.0.1 ou ::1")


def create_sandbox(server_dsn: str) -> str:
    if "sandbox" not in SANDBOX_DB:
        raise RuntimeError("a base de baseline tem de conter 'sandbox'")
    _require_loopback_dsn(server_dsn)
    with psycopg.connect(server_dsn, autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(SANDBOX_DB))
        )
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(SANDBOX_DB)))
    admin = _sandbox_admin_dsn(server_dsn)
    apply_migrations(admin, SANDBOX_PASSWORD)
    load_seed(admin)
    # Baseline ingénua: sem isolamento por vendedor na base (sandbox descartável).
    with psycopg.connect(admin, autocommit=True) as conn:
        for (table,) in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'qs_private'"
        ).fetchall():
            conn.execute(
                sql.SQL("ALTER TABLE qs_private.{} NO FORCE ROW LEVEL SECURITY").format(
                    sql.Identifier(table)
                )
            )
            conn.execute(
                sql.SQL("ALTER TABLE qs_private.{} DISABLE ROW LEVEL SECURITY").format(
                    sql.Identifier(table)
                )
            )
    return admin


def run_attack(admin_dsn: str, attack_sql: str) -> dict[str, object]:
    with psycopg.connect(admin_dsn) as conn:
        try:
            conn.execute("SET statement_timeout = '5s'")  # guarda do runner, não da baseline
            conn.execute("SET search_path = qs_api, qs_private, public")  # nomes como na app
            cursor = conn.execute(attack_sql)
            rows = cursor.fetchall() if cursor.description else []
            return {"outcome": "executado", "row_count": len(rows), "returned_rows": bool(rows)}
        except psycopg.Error as exc:
            return {
                "outcome": "erro",
                "row_count": 0,
                "returned_rows": False,
                "error": type(exc).__name__,
            }
        finally:
            conn.rollback()


def main() -> int:
    server_dsn = os.environ.get("QS_SANDBOX_ADMIN_DSN", "")
    if not server_dsn:
        print("Defina QS_SANDBOX_ADMIN_DSN (superuser do servidor local).")
        return 2
    admin = create_sandbox(server_dsn)
    attacks = [q for q in load_questions() if q["attack_sql"]]
    results = []
    for q in attacks:
        outcome = run_attack(admin, str(q["attack_sql"]))
        results.append({"id": q["id"], "sql": q["attack_sql"], "expect": q["expect"], **outcome})
    passed_through = sum(1 for r in results if r["outcome"] == "executado")
    report = {
        "kind": "baseline_insegura_sandbox",
        "database": SANDBOX_DB,
        "warning": "NÃO usar em produção. Sem validador, sem RLS, sem read-only.",
        "attacks_total": len(results),
        "attacks_executed_by_baseline": passed_through,
        "items": results,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / "baseline-sandbox.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"baseline: {passed_through}/{len(results)} ataques executados sem protecção -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
