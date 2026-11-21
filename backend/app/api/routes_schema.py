"""GET /schema/semantic: definições de métricas e schema visível para o papel autenticado."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from backend.app.auth.dependencies import get_principal
from backend.app.auth.tokens import Principal
from backend.app.semantic.view import build_role_view

router = APIRouter(prefix="/schema", tags=["schema"])


@router.get("/semantic")
def semantic_schema(
    request: Request, principal: Annotated[Principal, Depends(get_principal)]
) -> dict[str, Any]:
    return build_role_view(request.app.state.semantic, principal.role)
