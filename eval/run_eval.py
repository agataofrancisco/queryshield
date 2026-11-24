"""Corre a avaliação contra o pipeline real e grava eval/reports/report-<provider>.json.

Perguntas: geração (mock) -> validação -> verificação -> execução com o executor de produção
-> comparação normalizada com o golden. Ataques: validador, depois a experiência de laboratório
(ablation) para ver qual camada travou cada um.

Uso (com QS_READER_DSN_TEMPLATE definido e eval/expected.jsonl gerado): python -m eval.run_eval
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.config import DEFAULT_SEMANTIC_DIR, Settings, seller_dsn
from backend.app.execution.errors import ExecutionError
from backend.app.execution.executor import SellerExecutors
from backend.app.generation.mock import MockGenerator
from backend.app.generation.models import GenerationError
from backend.app.generation.service import build_proposal
from backend.app.semantic.loader import load_semantic_model
from backend.app.semantic.models import Role
from backend.app.validation.ast_validator import validate_sql
from backend.app.verification.checks import verify_semantics
from eval.ablation import raw_attempt
from eval.build_questions import QUESTIONS_PATH, load_questions
from eval.normalize import percentile, results_equal

EVAL_DIR = Path(__file__).resolve().parent
EXPECTED_PATH = EVAL_DIR / "expected.jsonl"
REPORTS_DIR = EVAL_DIR / "reports"
SEED = 20261120


def _load_expected(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            out[record["id"]] = record
    return out


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "desconhecido"


def _answer_question(
    q: dict[str, Any],
    model: Any,
    generator: MockGenerator,
    executor: SellerExecutors,
    expected: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    role = Role(q["role"])
    seller = int(q["seller_id"])
    started = time.perf_counter()
    record: dict[str, Any] = {
        "id": q["id"],
        "category": q["category"],
        "expect": q["expect"],
        "question": q["question"],
    }
    try:
        proposal = build_proposal(q["question"], role, model, generator)
    except GenerationError as exc:
        record.update(outcome="generation_error", code=exc.code, sql_valid=None, correct=False)
        record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return record
    record["proposal_status"] = proposal["status"]
    if proposal["status"] == "needs_clarification":
        outcome, correct, sql_valid = "clarification", q["expect"] == "clarification", None
    elif proposal["status"] != "generated":
        outcome = "unsupported"
        correct, sql_valid = q["expect"] == "no_leak", None
    else:
        check = validate_sql(proposal["sql"], role, model, proposal["parameters"])
        sql_valid = check.ok
        record["metric_warnings"] = (
            [w["code"] for w in verify_semantics(check.canonical_sql, model)] if check.ok else []
        )
        if not check.ok:
            outcome = "blocked_validator"
            record["issues"] = [i.code for i in check.issues]
            correct = q["expect"] == "no_leak"
        else:
            try:
                result = executor.execute(
                    check.canonical_sql, proposal["parameters"] or None, seller
                )
                outcome = "answered"
                if q["expect"] == "rows":
                    golden = expected[q["id"]]
                    correct = results_equal(golden["rows"], result.rows, ordered=golden["ordered"])
                    record["row_count"] = result.row_count
                else:
                    correct = False
            except ExecutionError as exc:
                outcome = "execution_error"
                correct = q["expect"] == "no_leak"
                record["code"] = exc.code
    record.update(outcome=outcome, correct=bool(correct), sql_valid=sql_valid)
    record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return record


def _run_attack(
    q: dict[str, Any], model: Any, template: str, seller_passwords: dict[int, str]
) -> dict[str, Any]:
    """Ataque: 1) validador; 2) se passou, experiência de laboratório com o validador ignorado.

    Passa se: o validador travar; ou a base de dados travar; ou (no_leak) não devolver linhas.
    """
    role = Role(q["role"])
    sql = str(q["attack_sql"])
    check = validate_sql(sql, role, model, None)
    if check.ok:
        validator_layer = "não bloqueado pelo validador"
    else:
        validator_layer = "validador: " + ", ".join(sorted({i.code for i in check.issues}))
    raw = raw_attempt(seller_dsn(template, int(q["seller_id"]), seller_passwords), sql)
    if check.ok:
        passed = raw.blocked or raw.row_count == 0
        if q["expect"] == "blocked":
            passed = raw.blocked
    else:
        passed = True
    return {
        "id": q["id"],
        "sql": sql,
        "expect": q["expect"],
        "note": q.get("note", ""),
        "validator": validator_layer,
        "validator_blocked": not check.ok,
        "database_layer_without_validator": raw.layer,
        "database_blocked": raw.blocked,
        "passed": passed,
    }


def run(template: str, seller_passwords: dict[int, str], provider: str = "mock") -> dict[str, Any]:
    model = load_semantic_model(DEFAULT_SEMANTIC_DIR)
    expected = _load_expected(EXPECTED_PATH)
    generator = MockGenerator()
    executor = SellerExecutors(
        template,
        (1, 2, 3),
        statement_timeout_ms=3000,
        max_rows=500,
        max_result_bytes=1_000_000,
        deadline_margin_ms=1000,
        seller_passwords=seller_passwords,
    )
    executor.open()
    questions = load_questions(QUESTIONS_PATH)
    answered: list[dict[str, Any]] = []
    attacks: list[dict[str, Any]] = []
    try:
        for q in questions:
            if q["attack_sql"]:
                attacks.append(_run_attack(q, model, template, seller_passwords))
            else:
                answered.append(_answer_question(q, model, generator, executor, expected))
    finally:
        executor.close()

    rows_items = [r for r in answered if r["expect"] == "rows"]
    generated = [r for r in answered if r.get("sql_valid") is not None]
    by_category: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "correct": 0})
    for r in answered:
        by_category[r["category"]]["n"] += 1
        by_category[r["category"]]["correct"] += int(r["correct"])
    latencies = [r["latency_ms"] for r in answered]
    metric_warnings = sum(len(r.get("metric_warnings", [])) for r in answered)
    report = {
        "provider": provider,
        "seed": SEED,
        "git_commit": _git_commit(),
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "questions_total": len(questions),
            "answerable": len(answered),
            "attacks": len(attacks),
            "expected_rows_questions": len(rows_items),
        },
        "metrics": {
            "execution_accuracy": _ratio(sum(r["correct"] for r in rows_items), len(rows_items)),
            "valid_sql_rate": _ratio(sum(1 for r in generated if r["sql_valid"]), len(generated)),
            "metric_definition_warnings": metric_warnings,
            "answered_but_wrong": sum(
                1 for r in answered if r["outcome"] == "answered" and not r["correct"]
            ),
            "unsupported": sum(1 for r in answered if r["outcome"] == "unsupported"),
            "latency_ms_p50": percentile(latencies, 0.5),
            "latency_ms_p95": percentile(latencies, 0.95),
            "cost": {
                "tokens": 0,
                "note": "provider mock: sem custo de LLM. TODO: medir com LLM real",
            },
        },
        "by_category": {
            k: {**v, "accuracy": _ratio(v["correct"], v["n"])}
            for k, v in sorted(by_category.items())
        },
        "attacks": {
            "total": len(attacks),
            "passed": sum(1 for a in attacks if a["passed"]),
            "blocked_by_validator": sum(1 for a in attacks if a["validator_blocked"]),
            "blocked_by_database_without_validator": sum(
                1 for a in attacks if a["database_blocked"]
            ),
            "items": attacks,
        },
        "answers": answered,
    }
    return report


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def main() -> int:
    settings = Settings.from_env(os.environ)
    if not settings.reader_dsn_template or not EXPECTED_PATH.exists():
        print(
            "Defina QS_READER_DSN_TEMPLATE e gere eval/expected.jsonl "
            "(python -m eval.build_expected)."
        )
        return 2
    report = run(settings.reader_dsn_template, dict(settings.seller_passwords))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"report-{report['provider']}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    m = report["metrics"]
    print(
        f"execution_accuracy={m['execution_accuracy']} valid_sql_rate={m['valid_sql_rate']} "
        f"p50={m['latency_ms_p50']}ms p95={m['latency_ms_p95']}ms"
    )
    print(
        f"ataques: {report['attacks']['passed']}/{report['attacks']['total']} passaram; "
        f"validador={report['attacks']['blocked_by_validator']} "
        f"base_de_dados_sem_validador={report['attacks']['blocked_by_database_without_validator']}"
    )
    print(f"relatório: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
