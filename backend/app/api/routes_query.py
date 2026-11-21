"""Endpoints de consulta. Nesta fase: validação (POST /query/validate)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.app.auth.dependencies import get_principal
from backend.app.auth.tokens import Principal
from backend.app.validation.ast_validator import validate_sql
from backend.app.validation.policy import MAX_SQL_LENGTH

router = APIRouter(prefix="/query", tags=["query"])


class ValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: Annotated[str, Field(max_length=MAX_SQL_LENGTH)]
    parameters: dict[str, Any] | None = None


@router.post("/validate")
def validate(
    body: ValidateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> dict[str, Any]:
    result = validate_sql(body.sql, principal.role, request.app.state.semantic, body.parameters)
    if result.ok:
        request.app.state.validated.add(principal.user, result.sql_hash)
    return result.as_dict()
