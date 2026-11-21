"""GET /health: estado do serviço e da base de dados. Não autenticado e sem detalhes de infra."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    executor = request.app.state.executor
    if executor is None:
        return {"status": "ok", "database": "not_configured"}
    reachable = executor.ping()
    return {
        "status": "ok" if reachable else "degraded",
        "database": "ok" if reachable else "unavailable",
    }
