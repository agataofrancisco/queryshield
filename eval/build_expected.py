"""Gera eval/expected.jsonl: resultados golden executados como o papel/tenant da pergunta.

Cada SQL golden passa primeiro pelo validador (se não passar, o build falha): um golden
inválido não pode tornar-se resultado esperado. A execução usa o mesmo executor de produção.

Uso (com QS_READER_DSN definido): python -m eval.build_expected
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from backend.app.config import DEFAULT_SEMANTIC_DIR
from backend.app.execution.errors import ExecutionError
from backend.app.execution.executor import QueryExecutor
from backend.app.semantic.loader import load_semantic_model
from backend.app.semantic.models import Role
from backend.app.validation.ast_validator import validate_sql
from eval.build_questions import QUESTIONS_PATH, load_questions
from eval.normalize import is_ordered_golden, normalize_rows

EVAL_DIR = Path(__file__).resolve().parent
EXPECTED_PATH = EVAL_DIR / "expected.jsonl"


class GoldenInvalid(RuntimeError):
    pass


def _jsonable(rows: list[tuple[object, ...]]) -> list[list[object]]:
    out: list[list[object]] = []
    for row in rows:
        out.append(
            [None if v is None else (v if isinstance(v, (bool, int, str)) else str(v)) for v in row]
        )
    return out


def build_expected(
    conninfo: str,
    output_path: Path = EXPECTED_PATH,
    questions_path: Path = QUESTIONS_PATH,
    semantic_dir: Path = DEFAULT_SEMANTIC_DIR,
) -> int:
    model = load_semantic_model(semantic_dir)
    executor = QueryExecutor(
        conninfo, statement_timeout_ms=5000, max_rows=5000, max_result_bytes=50_000_000
    )
    executor.open()
    records: list[str] = []
    try:
        for question in load_questions(questions_path):
            if question["expect"] != "rows":
                continue
            role = Role(question["role"])
            params = dict(question["parameters"] or {})
            golden = str(question["golden_sql"])
            check = validate_sql(golden, role, model, params or None)
            if not check.ok:
                raise GoldenInvalid(
                    f"{question['id']}: golden inválido {[i.code for i in check.issues]}"
                )
            try:
                result = executor.execute(
                    check.canonical_sql, params or None, int(question["seller_id"])
                )
            except ExecutionError as exc:
                raise GoldenInvalid(
                    f"{question['id']}: execução golden falhou ({exc.code})"
                ) from exc
            rows = normalize_rows(result.rows)
            payload = {
                "id": question["id"],
                "columns": list(result.columns),
                "rows": _jsonable(rows),
                "ordered": is_ordered_golden(golden),
                "sha256": hashlib.sha256(
                    json.dumps(_jsonable(rows), ensure_ascii=False).encode("utf-8")
                ).hexdigest(),
            }
            records.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    finally:
        executor.close()
    output_path.write_text("\n".join(records) + "\n", encoding="utf-8")
    return len(records)


def main() -> int:
    conninfo = os.environ.get("QS_READER_DSN", "")
    if not conninfo:
        print("QS_READER_DSN não definido.")
        return 2
    count = build_expected(conninfo)
    print(f"Resultados golden gravados: {count} em {EXPECTED_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
