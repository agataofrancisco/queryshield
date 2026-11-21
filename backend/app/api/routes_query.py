"""Endpoints de consulta: validar, gerar proposta, executar (ou EXPLAIN) e histórico.

Regra de execução: o SQL é SEMPRE validado de novo no pedido. Um validated_hash enviado pelo
cliente só serve para provar que o SQL não mudou; se não corresponder, o pedido é recusado.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.errors import ApiError
from backend.app.auth.dependencies import get_principal
from backend.app.auth.tokens import Principal
from backend.app.execution.errors import ExecutionError
from backend.app.generation.models import GenerationError
from backend.app.generation.service import MAX_QUESTION_CHARS, build_proposal
from backend.app.validation.ast_validator import ValidationResult, validate_sql
from backend.app.validation.policy import MAX_SQL_LENGTH

router = APIRouter(prefix="/query", tags=["query"])

EXECUTION_STATUS = {
    "query_timeout": 504,
    "permission_denied": 403,
    "read_only_violation": 403,
    "database_unavailable": 503,
    "execution_failed": 422,
    "result_too_large": 413,
}


class ValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: Annotated[str, Field(max_length=MAX_SQL_LENGTH)]
    parameters: dict[str, Any] | None = None


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Annotated[str, Field(max_length=MAX_QUESTION_CHARS)]


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: Annotated[str, Field(max_length=MAX_SQL_LENGTH)]
    parameters: dict[str, Any] | None = None
    validated_hash: Annotated[str | None, Field(max_length=64)] = None
    explain: bool = False
    question: Annotated[str | None, Field(max_length=MAX_QUESTION_CHARS)] = None


def _validate(
    request: Request, principal: Principal, sql: str, parameters: dict[str, Any] | None
) -> ValidationResult:
    result = validate_sql(sql, principal.role, request.app.state.semantic, parameters)
    if result.ok:
        request.app.state.validated.add(principal.user, result.sql_hash)
    return result


@router.post("/validate")
def validate(
    body: ValidateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> dict[str, Any]:
    return _validate(request, principal, body.sql, body.parameters).as_dict()


@router.post("/generate")
def generate(
    body: GenerateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> dict[str, Any]:
    try:
        proposal = build_proposal(
            body.question, principal.role, request.app.state.semantic, request.app.state.generator
        )
    except GenerationError as exc:
        status = 422 if exc.code == "invalid_input" else 502
        raise ApiError(status, exc.code, exc.message) from exc
    validation = None
    if proposal["sql"] is not None:
        validation = _validate(
            request, principal, proposal["sql"], proposal["parameters"]
        ).as_dict()
    request.app.state.history.record(
        principal.user,
        question=body.question,
        sql=proposal["sql"],
        status=proposal["status"],
    )
    return {**proposal, "validation": validation}


@router.post("/execute")
def execute(
    body: ExecuteRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> dict[str, Any]:
    executor = request.app.state.executor
    if executor is None:
        raise ApiError(503, "database_unavailable", "Base de dados não configurada.")
    result = _validate(request, principal, body.sql, body.parameters)
    if not result.ok:
        raise ApiError(
            422,
            "validation_failed",
            "A consulta não passou na validação.",
            details={"issues": [i.as_dict() for i in result.issues]},
        )
    if body.validated_hash is not None and body.validated_hash != result.sql_hash:
        raise ApiError(409, "not_validated", "O SQL foi alterado desde a validação.")
    history_store = request.app.state.history
    try:
        if body.explain:
            plan = executor.explain(result.canonical_sql, body.parameters, principal.seller_id)
            history_store.record(
                principal.user, question=body.question, sql=result.canonical_sql, status="explained"
            )
            return {"mode": "explain", "sql_hash": result.sql_hash, "plan": plan}
        outcome = executor.execute(result.canonical_sql, body.parameters, principal.seller_id)
    except ExecutionError as exc:
        history_store.record(
            principal.user, question=body.question, sql=result.canonical_sql, status="failed"
        )
        raise ApiError(EXECUTION_STATUS.get(exc.code, 422), exc.code, exc.message) from exc
    history_store.record(
        principal.user,
        question=body.question,
        sql=result.canonical_sql,
        status="executed",
        row_count=outcome.row_count,
    )
    return {
        "mode": "execute",
        "sql_hash": result.sql_hash,
        "columns": list(outcome.columns),
        "rows": outcome.rows,
        "row_count": outcome.row_count,
        "truncated": outcome.truncated,
        "elapsed_ms": outcome.elapsed_ms,
        "warnings": [],
    }


@router.get("/history")
def history(
    request: Request, principal: Annotated[Principal, Depends(get_principal)]
) -> dict[str, Any]:
    return {"items": request.app.state.history.list_for(principal.user)}
