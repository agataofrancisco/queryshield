"""Gera eval/questions.jsonl a partir do catálogo (determinístico).

Uso: python -m eval.build_questions
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.catalog import Question, build_catalog

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = EVAL_DIR / "questions.jsonl"


def question_record(question: Question) -> dict[str, object]:
    return {
        "id": question.id,
        "category": question.category,
        "role": question.role,
        "seller_id": question.seller_id,
        "question": question.question,
        "expect": question.expect,
        "golden_sql": question.golden_sql,
        "parameters": question.parameters,
        "attack_sql": question.attack_sql,
        "note": question.note,
    }


def render_jsonl(questions: list[Question]) -> str:
    lines = [json.dumps(question_record(q), ensure_ascii=False, sort_keys=True) for q in questions]
    return "\n".join(lines) + "\n"


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def main() -> int:
    QUESTIONS_PATH.write_text(render_jsonl(build_catalog()), encoding="utf-8")
    print(f"Escritas {len(load_questions())} perguntas em {QUESTIONS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
